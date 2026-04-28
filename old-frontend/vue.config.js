const webpack = require('webpack')

module.exports = {
  // Public source maps so Faro / Grafana resolve minified stack traces.
  productionSourceMap: true,
  // web-vitals (pulled in by @grafana/faro-web-sdk) ships ES2022 class
  // fields that webpack 4's parser cannot read raw. Force babel-loader
  // to transpile both packages.
  transpileDependencies: [
    /[\\/]node_modules[\\/]web-vitals[\\/]/,
    /[\\/]node_modules[\\/]@grafana[\\/]faro-web-sdk[\\/]/
  ],
  configureWebpack: {
    plugins: [
      new webpack.DefinePlugin({
        // Build-time injection of the IsardVDI release id so Faro tags
        // every event with the exact frontend bundle that produced it.
        __APP_VERSION__: JSON.stringify(process.env.SRC_VERSION_ID || 'dev')
      })
    ],
    module: {
      rules: [
        {
          test: /\.mjs$/,
          include: /node_modules/,
          type: 'javascript/auto'
        }
      ]
    }
  },
  chainWebpack: config => {
    config.module
      .rule('vue')
      .use('vue-loader')
      .loader('vue-loader')
      .tap(options => {
        options.transformAssetUrls = {
          img: 'src',
          image: 'xlink:href',
          'b-avatar': 'src',
          'b-img': 'src',
          'b-img-lazy': ['src', 'blank-src'],
          'b-card': 'img-src',
          'b-card-img': 'src',
          'b-card-img-lazy': ['src', 'blank-src'],
          'b-carousel-slide': 'img-src',
          'b-embed': 'src'
        }

        return options
      })
  },

  pluginOptions: {
    i18n: {
      locale: 'en',
      fallbackLocale: 'en',
      localeDir: 'locales',
      enableInSFC: false
    }
  },

  devServer: {
    disableHostCheck: true,
    public: process.env.WDS_PUBLIC || 'https://localhost:443'
  }
}
