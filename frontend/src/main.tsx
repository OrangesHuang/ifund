import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import 'dayjs/locale/zh-cn'
import App from './App'
import './index.css'

// 子路径部署(/ifund/): 路由基座跟随部署 base, 否则 navigate('/') 会把浏览器带回根路径
// dev 时 BASE_URL 为 '/', basename 留空等同默认
const routerBase = import.meta.env.BASE_URL === '/' ? '' : import.meta.env.BASE_URL.replace(/\/+$/, '')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: { colorPrimary: '#1677ff' },
      }}
    >
      <BrowserRouter basename={routerBase}>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>,
)
