const RAW_STATUS_RE = /\b(?:text|bg|border|ring)-(?:amber|emerald|rose|red|yellow)-(?:50|100|200|300|400|500|600|700|800|900|950)(?:\/\d+)?\b/

function checkString(context, node, value) {
  if (typeof value !== 'string' || !RAW_STATUS_RE.test(value)) return
  context.report({
    node,
    message:
      'Use semantic status tokens (success, warning, destructive, info) instead of raw palette status classes.',
  })
}

module.exports = {
  meta: {
    name: 'design-system',
  },
  rules: {
    'no-raw-status-colors': {
      create(context) {
        return {
          Literal(node) {
            checkString(context, node, node.value)
          },
          TemplateElement(node) {
            checkString(context, node, node.value && node.value.raw)
          },
        }
      },
    },
  },
}
