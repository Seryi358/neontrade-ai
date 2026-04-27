const React = require('react');

function MockSvg(props) {
  return React.createElement('svg', props, props.children);
}

module.exports = MockSvg;
module.exports.default = MockSvg;
module.exports.Svg = MockSvg;
module.exports.Path = 'Path';
module.exports.Circle = 'Circle';
module.exports.Line = 'Line';
module.exports.G = 'G';
