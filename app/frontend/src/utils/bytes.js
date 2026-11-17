const formato = new Intl.NumberFormat('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const UNIDADES = ['KB', 'MB', 'GB', 'TB']

// Base 1024 y coma decimal, como escribe el servidor (filesizeformat)
export function formatBytes(bytes) {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  let valor = bytes / 1024
  let i = 0
  while (valor >= 1024 && i < UNIDADES.length - 1) {
    valor /= 1024
    i++
  }
  return `${formato.format(valor)} ${UNIDADES[i]}`
}
