module.exports = {
  presets: [
    '@vue/cli-plugin-babel/preset'
  ],
  // web-vitals 5.x (transitive dep of @grafana/faro-web-sdk) ships
  // ES2022 class fields. The project's browserslist target supports
  // them, so @babel/preset-env skips transpilation — which leaves
  // webpack 4's acorn parser unable to read the file. Force
  // class-fields transpilation regardless of target so webpack can
  // parse the file.
  plugins: [
    '@babel/plugin-proposal-class-properties'
  ]
}
