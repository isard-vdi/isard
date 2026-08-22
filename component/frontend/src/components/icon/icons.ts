import { defineAsyncComponent, type Component } from 'vue'

const FALLBACK = 'face-smile'

// A dynamic `import()` on a template literal compiles to this same glob, but
// inlined in the loader body — which rebuilt 1182 closures for every icon that
// mounted. At module scope it is built once.
const modules = import.meta.glob<Component>('@/assets/icons/*.svg', {
  query: '?component',
  import: 'default'
})

const loaders = new Map(
  Object.entries(modules).map(([path, load]) => [
    path.slice(path.lastIndexOf('/') + 1, -'.svg'.length),
    load
  ])
)

// Shared per name so every instance of an icon resolves to one component type,
// instead of each running its own load and remounting on every re-render.
const cache = new Map<string, Component>()

export function getIcon(name: string): Component {
  const cached = cache.get(name)
  if (cached) return cached

  const component = defineAsyncComponent(() => {
    const load = loaders.get(name)
    if (load) return load()

    console.error(`Failed load icon '${name}': no such icon, using '${FALLBACK}'`)
    const fallback = loaders.get(FALLBACK)
    if (fallback) return fallback()
    return Promise.reject(new Error(`Icon '${name}' and fallback '${FALLBACK}' are both missing`))
  })

  cache.set(name, component)
  return component
}
