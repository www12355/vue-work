#!/usr/bin/env node
/**
 * 代理配置同步服务：监听来自前端的代理配置更新请求，
 * 将配置写入到 proxy.config.json，使 Vite 能够立即应用新规则。
 *
 * 用法：
 *   node scripts/proxy-config-server.js
 * 或在 package.json 中添加：
 *   "scripts": { "proxy-sync": "node scripts/proxy-config-server.js" }
 *
 * 前端通过 POST /api/proxy-config 发送配置，该服务将其保存到磁盘。
 */

const fs = require('fs')
const path = require('path')
const http = require('http')

const CONFIG_FILE = path.join(__dirname, '../proxy.config.json')
const PORT = 3001

const server = http.createServer((req, res) => {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type')

  if (req.method === 'OPTIONS') {
    res.writeHead(200)
    res.end()
    return
  }

  if (req.method === 'GET' && req.url === '/api/proxy-config') {
    // 读取磁盘上的真实配置
    try {
      const content = fs.readFileSync(CONFIG_FILE, 'utf-8')
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(content)
      console.log(`✓ 读取 proxy.config.json (${new Date().toLocaleTimeString()})`)
    } catch (err) {
      res.writeHead(404, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ error: 'Config file not found' }))
    }
    return
  }

  if (req.method === 'POST' && req.url === '/api/proxy-config') {
    // 写入新配置
    let body = ''
    req.on('data', chunk => {
      body += chunk
    })
    req.on('end', () => {
      try {
        // 验证 JSON 格式
        const config = JSON.parse(body)
        if (!Array.isArray(config)) {
          throw new Error('Config must be an array')
        }

        // 写入文件
        fs.writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2))
        console.log(`✓ proxy.config.json 已更新 (${new Date().toLocaleTimeString()})`)

        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ success: true, message: 'Config saved' }))
      } catch (err) {
        console.error('✗ 保存配置失败:', err.message)
        res.writeHead(400, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ error: err.message }))
      }
    })
    return
  }

  res.writeHead(404)
  res.end('Not Found')
})

server.listen(PORT, '127.0.0.1', () => {
  console.log(`\n🔄 代理配置同步服务运行在 http://127.0.0.1:${PORT}`)
  console.log(`📝 前端修改代理规则后会自动同步到 proxy.config.json\n`)
})

process.on('SIGINT', () => {
  console.log('\n🛑 同步服务已停止')
  process.exit(0)
})
