const { merge } = require('webpack-merge');
const common = require('./webpack.config.cjs');
const TerserPlugin = require('terser-webpack-plugin');
const WebBundlePlugin = require('webbundle-webpack-plugin');
const { WebBundleId, parsePemKey } = require('wbn-sign');

// Get shared environment variables
// Access the non-enumerable property
const sharedEnv = common.sharedEnv || {};
const privateKey = sharedEnv.privateKey;

// Configure web bundle plugin
let webBundlePlugin;
if (privateKey) {
  const parsedPrivateKey = parsePemKey(privateKey);
  webBundlePlugin = new WebBundlePlugin({
    baseURL: new WebBundleId(parsedPrivateKey).serializeWithIsolatedWebAppOrigin(),
    static: { dir: 'assets' },
    output: 'app.swbn',
    integrityBlockSign: { key: parsedPrivateKey }
  });
} else {
  webBundlePlugin = new WebBundlePlugin({
    baseURL: '/',
    output: 'app.wbn',
  });
}

// Merge configurations
module.exports = merge(common, {
  mode: 'production',
  optimization: {
    minimize: true,
    minimizer: [
      new TerserPlugin({
        terserOptions: {
          format: { 
            comments: false,
            ascii_only: true
          },
          compress: {
            drop_console: true,
            drop_debugger: true,
            pure_funcs: [],
            passes: 3,
            unsafe: true,
            unsafe_math: true,
            unsafe_methods: true,
            unsafe_proto: true,
            unsafe_regexp: true,
            collapse_vars: true,
            dead_code: true,
            reduce_vars: true,
            booleans_as_integers: true
          },
          mangle: {
            eval: false,
            keep_classnames: false,
            keep_fnames: false,
            toplevel: true,
            safari10: true,
            properties: false
          },
          ecma: 2020,
          module: true
        },
        extractComments: false,
      }),
    ],
  },
  output: {
    clean: true
  },
  plugins: [
    webBundlePlugin,
  ]
}); 