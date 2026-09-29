// Requiredness is probed behaviourally instead of read off the schema: zod
// exposes no flag that survives `.min(1)`, `.regex()` or `.refine()`, so a
// field counts as required when it rejects every value a user could leave it
// at. `_zod.def` is zod v4's schema descriptor.
import type * as z from 'zod'

interface ZodDef {
  type?: string
  in?: unknown
  innerType?: unknown
  shape?: Record<string, unknown>
  element?: unknown
  items?: unknown[]
  valueType?: unknown
}

const TRANSPARENT_WRAPPERS = new Set([
  'optional',
  'nullable',
  'default',
  'prefault',
  'readonly',
  'nonoptional',
  'catch'
])

const MAX_UNWRAP_DEPTH = 20

function defOf(schema: unknown): ZodDef | undefined {
  return (schema as { _zod?: { def?: ZodDef } } | undefined)?._zod?.def
}

// `.refine()` and `.superRefine()` append checks to the same node in zod v4,
// so only pipes and the optional family need peeling.
function unwrap(schema: unknown): unknown {
  let current = schema
  for (let depth = 0; depth < MAX_UNWRAP_DEPTH; depth++) {
    const def = defOf(current)
    if (!def) return undefined
    if (def.type === 'pipe') {
      current = def.in
      continue
    }
    if (def.type && TRANSPARENT_WRAPPERS.has(def.type)) {
      current = def.innerType
      continue
    }
    return current
  }
  return undefined
}

/** `'a.b[0].c'` → `['a', 'b', 0, 'c']`. TanStack emits bracketed array paths. */
export function tokenizePath(path: string): (string | number)[] {
  const tokens: (string | number)[] = []
  for (const part of path.split('.')) {
    if (!part) continue
    const matcher = /([^[\]]+)|\[(\d+)\]/g
    let match: RegExpExecArray | null
    while ((match = matcher.exec(part)) !== null) {
      tokens.push(match[1] !== undefined ? match[1] : Number(match[2]))
    }
  }
  return tokens
}

function childAt(schema: unknown, token: string | number): unknown {
  const def = defOf(unwrap(schema))
  if (!def) return undefined
  if (typeof token === 'number') {
    if (def.type === 'array') return def.element
    if (def.type === 'tuple') return def.items?.[token]
    return undefined
  }
  if (def.type === 'object') return def.shape?.[token]
  if (def.type === 'record') return def.valueType
  return undefined
}

/** The sub-schema at a dotted or bracketed path, or undefined when unreachable. */
export function schemaAtPath(root: unknown, path: string): unknown {
  const tokens = tokenizePath(path)
  if (tokens.length === 0) return undefined
  let current: unknown = root
  for (const token of tokens) {
    current = childAt(current, token)
    if (current === undefined || current === null) return undefined
  }
  return current
}

function accepts(schema: z.ZodType, value: unknown): boolean {
  try {
    return schema.safeParse(value).success
  } catch {
    // A hand-written refinement on `z.any()` can throw on a probe value.
    return false
  }
}

/**
 * Whether the field at `path` rejects every empty value a user could submit.
 *
 * A missing schema, an unresolvable path or a field that tolerates emptiness
 * all answer `false`: the marker stays silent rather than guessing.
 */
export function isFieldRequired(root: unknown, path: string | undefined): boolean {
  if (!root || !path) return false

  const field = schemaAtPath(root, path) as z.ZodType | undefined
  if (!field) return false

  if (accepts(field, undefined)) return false
  if (accepts(field, '')) return false
  if (accepts(field, [])) return false

  // A plain `z.boolean()` takes both states, so a switch is never required,
  // while `z.literal(true)` and `z.boolean().refine(v => v)` still are.
  if (accepts(field, false) && accepts(field, true)) return false

  return true
}
