import axios from 'axios'

// 统一 axios 实例：baseURL=部署路径+/api(开发 /api 不变, 生产 /ifund/api)，注入 JWT，401 跳登录
const request = axios.create({
  baseURL: `${import.meta.env.BASE_URL}api`,
  timeout: 30000,
})

// 登录页完整路径(子路径部署下是 /ifund/login, 不是 /login, 否则会跳到别的应用)
const loginPath = `${import.meta.env.BASE_URL}login`

request.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

request.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      if (window.location.pathname !== loginPath) {
        window.location.href = loginPath
      }
    }
    return Promise.reject(error)
  },
)

export default request
