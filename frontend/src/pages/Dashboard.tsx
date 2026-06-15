import { useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { Button, Layout, Menu } from 'antd'
import {
  ApartmentOutlined,
  CalendarOutlined,
  DeploymentUnitOutlined,
  FundOutlined,
  KeyOutlined,
  LogoutOutlined,
} from '@ant-design/icons'
import { FundPage } from './fund'
import WorkbenchPage from './workbench/WorkbenchPage'
import IndustryPage from './IndustryPage'
import TokensPage from './TokensPage'
import TradeCalendar from './TradeCalendar'

const { Header, Sider, Content } = Layout

export default function Dashboard() {
  const navigate = useNavigate()
  const [selected, setSelected] = useState('fund')
  const [collapsed, setCollapsed] = useState(false)

  const logout = () => {
    localStorage.removeItem('token')
    navigate('/login')
  }

  const go = (key: string) => {
    setSelected(key)
    navigate(key === 'fund' ? '/' : `/${key}`)
  }

  return (
    // 固定视口高度：仅内容区滚动，Header/侧边栏不随滚动移动
    <Layout style={{ height: '100vh' }}>
      <Header className="flex items-center justify-between" style={{ paddingInline: 16, flexShrink: 0 }}>
        <span style={{ color: '#fff', fontSize: 18, fontWeight: 600 }}>iFund</span>
        <Button icon={<LogoutOutlined />} onClick={logout} ghost size="small">
          退出
        </Button>
      </Header>
      <Layout>
        <Sider
          width={160}
          theme="dark"
          collapsible
          collapsed={collapsed}
          onCollapse={setCollapsed}
        >
          <Menu
            mode="inline"
            theme="dark"
            selectedKeys={[selected]}
            onClick={(e) => go(e.key)}
            items={[
              { key: 'fund', icon: <FundOutlined />, label: '基金管理' },
              { key: 'workbench', icon: <DeploymentUnitOutlined />, label: '组合分析' },
              { key: 'trade_calendar', icon: <CalendarOutlined />, label: '交易日历' },
              { key: 'industry', icon: <ApartmentOutlined />, label: '行业映射' },
              { key: 'tokens', icon: <KeyOutlined />, label: '访问令牌' },
            ]}
          />
        </Sider>
        <Content style={{ padding: 16, overflow: 'auto' }}>
          <Routes>
            <Route path="/" element={<FundPage />} />
            <Route path="/workbench" element={<WorkbenchPage />} />
            <Route path="/trade_calendar" element={<TradeCalendar />} />
            <Route path="/industry" element={<IndustryPage />} />
            <Route path="/tokens" element={<TokensPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}
