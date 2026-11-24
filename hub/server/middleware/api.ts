export default defineEventHandler(event => {
  const url = getRequestURL(event)
  if (!url.pathname.startsWith('/api/')) return
  const base = useRuntimeConfig(event).storageUrl.replace(/\/$/, '')
  return proxyRequest(event, `${base}${url.pathname}${url.search}`)
})
