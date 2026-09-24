const RAW_STATUS_RE = /\b(?:text|bg|border|ring)-(?:amber|emerald|rose|red|yellow)-(?:50|100|200|300|400|500|600|700|800|900|950)(?:\/\d+)?\b/

// The radius steps B-P6 migrated off: they are the shadcn defaults, not the product's scale, and
// leaving one behind is how a dialog footer ends up a pixel off its own content. The named steps
// (well, control, panel) are the only radius tokens this app should name.
const RAW_RADIUS_RE = /\brounded-(?:[btlrse]{1,2}-)?(?:lg|xl|2xl)\b/

// One reporter per rule: sharing a single check made every rule report every other rule's
// findings, which is why a radius problem used to be blamed on the status rule.
function reportMatches(context, node, value, pattern, message) {
  if (typeof value !== 'string' || !pattern.test(value)) return
  context.report({ node, message })
}

const STATUS_MESSAGE =
  'Use semantic status tokens (success, warning, destructive, info) instead of raw palette status classes.'
// Worded without spelling a matching class: a rule that names the pattern it forbids reports
// itself, because this plugin file is linted too.
const RADIUS_MESSAGE =
  'Use the named radius scale (well, control, panel) instead of the ad-hoc lg/xl/2xl steps: a raw step left behind is how a dialog footer ends up off its own content.'

function forEachString(context, pattern, message) {
  const visit = (node, value) => reportMatches(context, node, value, pattern, message)
  return {
    Literal(node) {
      visit(node, node.value)
    },
    TemplateElement(node) {
      visit(node, node.value && node.value.raw)
    },
  }
}

module.exports = {
  meta: {
    name: 'design-system',
  },
  rules: {
    'no-raw-status-colors': {
      create: (context) => forEachString(context, RAW_STATUS_RE, STATUS_MESSAGE),
    },
    'no-raw-radius-steps': {
      create: (context) => forEachString(context, RAW_RADIUS_RE, RADIUS_MESSAGE),
    },
  },
}
