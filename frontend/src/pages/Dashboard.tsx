import { useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { Button, Layout, Menu } from 'antd'
import {
  CalendarOutlined,
  FilterOutlined,
  FundOutlined,
  KeyOutlined,
  LogoutOutlined,
} from '@ant-design/icons'
import { FundPage } from './fund'
import ScreenPage from './screen/ScreenPage'
import TokensPage from './TokensPage'
import TradeCalendar from './TradeCalendar'

const { Header, Sider, Content } = Layout

export default function Dashboard() {
  const navigate = useNavigate()
  const [selected, setSelected] = useState('fund')

  const logout = () => {
    localStorage.removeItem('token')
    navigate('/login')
  }

  const go = (key: string) => {
    setSelected(key)
    navigate(key === 'fund' ? '/' : `/${key}`)
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header className="flex items-center justify-between" style={{ paddingInline: 16 }}>
        <span style={{ color: '#fff', fontSize: 18, fontWeight: 600 }}>iFund</span>
        <Button icon={<LogoutOutlined />} onClick={logout} ghost size="small">
          退出
        </Button>
      </Header>
      <Layout>
        <Sider width={160} theme="dark">
          <Menu
            mode="inline"
            theme="dark"
            selectedKeys={[selected]}
            onClick={(e) => go(e.key)}
            items={[
              { key: 'fund', icon: <FundOutlined />, label: '基金管理' },
              { key: 'screen', icon: <FilterOutlined />, label: '基金筛选' },
              { key: 'trade_calendar', icon: <CalendarOutlined />, label: '交易日历' },
              { key: 'tokens', icon: <KeyOutlined />, label: '访问令牌' },
            ]}
          />
        </Sider>
        <Content style={{ padding: 16, overflow: 'auto' }}>
          <Routes>
            <Route path="/" element={<FundPage />} />
            <Route path="/screen" element={<ScreenPage />} />
            <Route path="/trade_calendar" element={<TradeCalendar />} />
            <Route path="/tokens" element={<TokensPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}
