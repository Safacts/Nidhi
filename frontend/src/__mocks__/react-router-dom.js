// Manual jest mock for react-router-dom (v7 is ESM-only and cannot be resolved
// by Create-React-App's jest). Provides a passthrough router surface so the real
// App composition (providers + PrivateRoute redirect) is still exercised.
const React = require('react');

module.exports = {
  BrowserRouter: ({ children }) => React.createElement(React.Fragment, null, children),
  Routes: ({ children }) => React.createElement(React.Fragment, null, children),
  Route: () => null,
  Navigate: () => null,
  useNavigate: () => jest.fn(),
  useLocation: () => ({ pathname: '/', search: '', hash: '' }),
  Link: ({ children, to }) => React.createElement('a', { href: to }, children),
};
