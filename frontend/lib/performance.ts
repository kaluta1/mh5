/**
 * Performance optimization utilities
 * For lightning-fast page loads across the entire application
 */

// Prefetch links on hover for instant navigation
export function setupLinkPrefetching() {
  if (typeof window === 'undefined') return

  const links = document.querySelectorAll('a[href]')
  links.forEach(link => {
    const href = link.getAttribute('href')
    if (!href || href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('tel:')) return

    // Prefetch on hover
    link.addEventListener('mouseenter', () => {
      const url = new URL(href, window.location.origin)
      if (url.origin === window.location.origin) {
        // Use Next.js router prefetch
        import('next/navigation').then(({ useRouter }) => {
          // Prefetch the route
          const linkElement = document.createElement('link')
          linkElement.rel = 'prefetch'
          linkElement.href = href
          document.head.appendChild(linkElement)
        }).catch(() => {})
      }
    }, { once: true })
  })
}

// Debounce function for performance
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout | null = null
  return function executedFunction(...args: Parameters<T>) {
    const later = () => {
      timeout = null
      func(...args)
    }
    if (timeout) clearTimeout(timeout)
    timeout = setTimeout(later, wait)
  }
}

// Throttle function for performance
export function throttle<T extends (...args: any[]) => any>(
  func: T,
  limit: number
): (...args: Parameters<T>) => void {
  let inThrottle: boolean
  return function executedFunction(...args: Parameters<T>) {
    if (!inThrottle) {
      func(...args)
      inThrottle = true
      setTimeout(() => (inThrottle = false), limit)
    }
  }
}

// Lazy load images with intersection observer
export function setupLazyImages() {
  if (typeof window === 'undefined' || !('IntersectionObserver' in window)) return

  const imageObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const img = entry.target as HTMLImageElement
        if (img.dataset.src) {
          img.src = img.dataset.src
          img.removeAttribute('data-src')
          observer.unobserve(img)
        }
      }
    })
  }, {
    rootMargin: '50px' // Start loading 50px before image enters viewport
  })

  document.querySelectorAll('img[data-src]').forEach(img => {
    imageObserver.observe(img)
  })
}

// Preload critical resources
export function preloadCriticalResources() {
  if (typeof window === 'undefined') return

  // Preload API endpoint
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'https://mh5-hbjp.onrender.com'
  const link = document.createElement('link')
  link.rel = 'preconnect'
  link.href = apiUrl
  link.crossOrigin = 'anonymous'
  document.head.appendChild(link)
}

// Initialize all performance optimizations
export function initPerformanceOptimizations() {
  if (typeof window === 'undefined') return

  // Setup optimizations after DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      setupLinkPrefetching()
      setupLazyImages()
      preloadCriticalResources()
    })
  } else {
      setupLinkPrefetching()
      setupLazyImages()
      preloadCriticalResources()
  }
}
