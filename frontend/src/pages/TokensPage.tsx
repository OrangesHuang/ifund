import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Input,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import { DeleteOutlined, KeyOutlined, PlusOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import request from '../api/request'

interface TokenItem {
  id: number
  name: string
  prefix: string
  revoked: boolean
  last_used_at: string | null
  created_at: string | null
}

export default function TokensPage() {
  const [tokens, setTokens] = useState<TokenItem[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  // 新建后服务端返回的明文（仅展示一次）
  const [plaintext, setPlaintext] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await request.get('/auth/tokens')
      setTokens(data ?? [])
    } catch {
      message.error('加载令牌列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const create = async () => {
    setCreating(true)
    try {
      const { data } = await request.post('/auth/tokens', { name: name.trim() })
      setPlaintext(data.token)
      setName('')
      await load()
    } catch {
      message.error('创建令牌失败')
    } finally {
      setCreating(false)
    }
  }

  const revoke = async (id: number) => {
    try {
      await request.delete(`/auth/tokens/${id}`)
      message.success('已吊销')
      await load()
    } catch {
      message.error('吊销失败')
    }
  }

  const columns: ColumnsType<TokenItem> = [
    { title: '名称', dataIndex: 'name', render: (v: string) => v || <span className="text-gray-400">（未命名）</span> },
    { title: '前缀', dataIndex: 'prefix', render: (v: string) => <code>{v}…</code> },
    {
      title: '状态',
      dataIndex: 'revoked',
      width: 90,
      render: (v: boolean) => (v ? <Tag color="red">已吊销</Tag> : <Tag color="green">有效</Tag>),
    },
    { title: '最近使用', dataIndex: 'last_used_at', render: (v: string | null) => v || '—' },
    { title: '创建时间', dataIndex: 'created_at', render: (v: string | null) => v || '—' },
    {
      title: '操作',
      width: 90,
      render: (_: unknown, row: TokenItem) =>
        row.revoked ? null : (
          <Popconfirm title="吊销后该令牌立即失效，确认？" onConfirm={() => revoke(row.id)}>
            <Button danger size="small" icon={<DeleteOutlined />}>
              吊销
            </Button>
          </Popconfirm>
        ),
    },
  ]

  return (
    <Card
      title={
        <Space>
          <KeyOutlined />
          个人访问令牌（PAT）
        </Space>
      }
      extra={
        <Space.Compact>
          <Input
            placeholder="令牌名称（可选）"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ width: 180 }}
          />
          <Button type="primary" icon={<PlusOutlined />} loading={creating} onClick={create}>
            新建令牌
          </Button>
        </Space.Compact>
      }
    >
      <Alert
        type="info"
        showIcon
        className="mb-3"
        message="供 OpenClaw 等本机 agent 通过 MCP 长期调用。令牌绑定当前账号，明文仅在创建时显示一次。"
      />
      <Table
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={tokens}
        pagination={false}
      />

      <Modal
        title="令牌已创建"
        open={!!plaintext}
        onOk={() => setPlaintext(null)}
        onCancel={() => setPlaintext(null)}
        okText="我已保存"
        cancelButtonProps={{ style: { display: 'none' } }}
      >
        <Alert
          type="warning"
          showIcon
          className="mb-3"
          message="请立即复制保存，此明文不会再次显示。"
        />
        <Typography.Paragraph copyable={{ text: plaintext ?? '' }} className="break-all">
          <code>{plaintext}</code>
        </Typography.Paragraph>
      </Modal>
    </Card>
  )
}
