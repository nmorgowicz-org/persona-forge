"""OpenVINO graph rewrite for static-capacity internal K/V state.

OpenVINO's MakeStateful pass rejects dynamic state shapes. Qwen3-TTS needs a
dynamic used-cache length, so this rewrite stores each layer's K/V in a static
capacity Variable while slicing the used prefix and updating only the positions
named by cache_position.
"""

from __future__ import annotations


def make_static_kv_stateful(
    model,
    *,
    num_layers: int,
    base_input_count: int,
    cache_position_index: int,
    max_seq: int,
    state_prefix: str,
):
    """Replace flat K/V parameters/results with static internal state variables.

    Expected positional contract:
      parameters: base inputs, k0, v0, k1, v1, ...
      results: hidden, present_k0, present_v0, present_k1, present_v1, ...
    """
    if max_seq <= 0:
        raise ValueError("max_seq must be positive")

    import numpy as np
    import openvino as ov
    from openvino import opset13 as ops
    from openvino.op.util import Variable, VariableInfo

    parameters = list(model.get_parameters())
    results = list(model.get_results())
    kv_count = 2 * num_layers
    if len(parameters) != base_input_count + kv_count:
        raise ValueError(
            f"expected {base_input_count + kv_count} parameters, found {len(parameters)}"
        )
    if len(results) != 1 + kv_count:
        raise ValueError(f"expected {1 + kv_count} results, found {len(results)}")
    if not 0 <= cache_position_index < base_input_count:
        raise ValueError("cache_position_index must identify a base input")

    cache_position = parameters[cache_position_index].output(0)
    first_position = ops.slice(
        cache_position,
        ops.constant([0], dtype=np.int64),
        ops.constant([1], dtype=np.int64),
        ops.constant([1], dtype=np.int64),
    )
    axis = ops.constant(2, dtype=np.int64)
    zero = ops.constant([0], dtype=np.int64)
    one = ops.constant([1], dtype=np.int64)
    sequence_axis = ops.constant([2], dtype=np.int64)

    sinks = []
    for index in range(kv_count):
        parameter = parameters[base_input_count + index]
        result = results[1 + index]
        present = result.input_value(0)
        shape = present.get_partial_shape()
        if shape.rank.is_dynamic or shape.rank.get_length() != 4:
            raise ValueError(f"K/V result {index} must have rank 4, found {shape}")
        kv_heads = shape[1].get_length()
        head_dim = shape[3].get_length()

        kind = "key" if index % 2 == 0 else "value"
        layer = index // 2
        info = VariableInfo()
        info.data_shape = ov.PartialShape([1, kv_heads, max_seq, head_dim])
        info.data_type = present.get_element_type()
        info.variable_id = f"{state_prefix}.layer{layer}.{kind}"
        variable = Variable(info)

        state = ops.read_value(variable)
        state.set_friendly_name(f"{info.variable_id}.read")
        used_prefix = ops.slice(state, zero, first_position, one, sequence_axis)
        parameter.output(0).replace(used_prefix.output(0))

        # `present` is the core's concatenated prior+new cache. cache_position
        # indexes exactly the newly generated positions for prefill and decode.
        new_values = ops.gather(present, cache_position, axis)
        updated_state = ops.scatter_update(state, cache_position, new_values, axis)
        assign = ops.assign(updated_state, variable)
        assign.set_friendly_name(f"{info.variable_id}.assign")
        sinks.append(assign)

    model.add_sinks(sinks)
    for result in results[1:]:
        model.remove_result(result)
    for parameter in parameters[base_input_count:]:
        model.remove_parameter(parameter)
    model.validate_nodes_and_infer_types()
    return model
