import pxToViewport from 'postcss-px-to-viewport-8-plugin'

/**
 * 移动端适配（开发步骤清单 5.5.1）：设计稿 375px，1px = 1/375 视口宽。
 * 桌面端预览时上限由 viewportWidth 控制，不会无限放大。
 */
export default {
  plugins: [
    pxToViewport({
      viewportWidth: 375,
      unitToConvert: 'px',
      unitPrecision: 5,
      propList: ['*'],
      viewportUnit: 'vw',
      fontViewportUnit: 'vw',
      selectorBlackList: ['.ignore-vw', '.van-'],
      minPixelValue: 1,
      mediaQuery: false,
      replace: true,
      exclude: [/node_modules\/echarts/],
      landscape: false
    })
  ]
}
