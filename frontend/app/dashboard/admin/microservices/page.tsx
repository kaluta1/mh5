\'use client\'

import { useEffect, useMemo, useState } from \'react\'
import { useRouter } from \'next/navigation\'
import { useAuth } from \'@/hooks/use-auth\'
import { Card, CardContent, CardHeader, CardTitle } from \'@/components/ui/card\'
import { Button } from \'@/components/ui/button\'
import { Badge } from \'@/components/ui/badge\'
import { Loader2, RefreshCcw, Server, Activity, AlertTriangle } from \'lucide-react\'
import { cn } from \'@/lib/utils\'

type ServiceStatus = \'healthy\' | \'unhealthy\' | \'unknown\'

interface ServiceDefinition {
  id: string
  name: string
  baseUrl: string
  healthPath: string
  description: string
}

interface ServiceState {
  status: ServiceStatus
  checkedAt?: string
  responseTimeMs?: number
  details?: string
}

const DEFAULT_TIMEOUT_MS = 5000

export default function MicroservicesPage() {
  const router = useRouter()
  const { user, isLoading } = useAuth()
  const [statuses, setStatuses] = useState<Record<string, ServiceState>>({})
  const [isChecking, setIsChecking] = useState(false)

  const services = useMemo<ServiceDefinition[]>(() => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || \'http://localhost:8000\'
    const feedBase = process.env.NEXT_PUBLIC_FEED_SERVICE_URL || \'http://localhost:8001\'

    return [
      {
        id: \'backend\',
        name: \'Main API\',
        baseUrl: apiBase,
        healthPath: \'/\',
        description: \'Core platform API (auth, contests, users, admin).\',
      },
      {
        id: \'feed\',
        name: \'Feed Microservice\',
        baseUrl: feedBase,
        healthPath: \'/health\',
        description: \'Groups, feed, and encrypted messaging service.\',
      },
    ]
  }, [])

  useEffect(() => {
    if (!isLoading) {
      if (!user) {
        router.push(\'/login\')
        return
      }
      if (!user.is_admin) {
        router.push(\'/dashboard\')
        return
      }
      checkAll()
    }
  }, [isLoading, user, router])

  const checkService = async (service: ServiceDefinition): Promise<ServiceState> => {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)
    const start = performance.now()

    try {
      const response = await fetch(`${service.baseUrl}${service.healthPath}`, {
        method: \'GET\',
        signal: controller.signal,
      })
      const elapsed = Math.round(performance.now() - start)
      let details: string | undefined

      try {
        const json = await response.json()
        details = json?.status || json?.service || response.statusText
      } catch {
        details = response.statusText
      }

      return {
        status: response.ok ? \'healthy\' : \'unhealthy\',
        checkedAt: new Date().toLocaleString(),
        responseTimeMs: elapsed,
        details,
      }
    } catch (error: any) {
      const elapsed = Math.round(performance.now() - start)
      const message = error?.name === \'AbortError\' ? \'Timeout\' : error?.message || \'Network error\'
      return {
        status: \'unhealthy\',
        checkedAt: new Date().toLocaleString(),
        responseTimeMs: elapsed,
        details: message,
      }
    } finally {
      clearTimeout(timeout)
    }
  }

  const checkAll = async () => {
    setIsChecking(true)
    try {
      const results = await Promise.all(services.map(async (service) => ({
        id: service.id,
        state: await checkService(service),
      })))
      setStatuses(prev => {
        const next = { ...prev }
        results.forEach(result => {
          next[result.id] = result.state
        })
        return next
      })
    } finally {
      setIsChecking(false)
    }
  }

  const renderStatus = (status: ServiceStatus) => {
    if (status === \'healthy\') {
      return <Badge className="bg-green-100 text-green-700">Healthy</Badge>
    }
    if (status === \'unhealthy\') {
      return <Badge className="bg-red-100 text-red-700">Down</Badge>
    }
    return <Badge className="bg-gray-100 text-gray-700">Unknown</Badge>
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="h-6 w-6 animate-spin text-myhigh5-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Microservices</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Live status of running services and health checks.
          </p>
        </div>
        <Button onClick={checkAll} disabled={isChecking} variant="outline" className="gap-2">
          {isChecking ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCcw className="h-4 w-4" />
          )}
          Refresh
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {services.map((service) => {
          const state = statuses[service.id]
          const status: ServiceStatus = state?.status || \'unknown\'
          return (
            <Card key={service.id} className="border-gray-200 dark:border-gray-700">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      "w-10 h-10 rounded-lg flex items-center justify-center",
                      status === \'healthy\' && "bg-green-100 text-green-600",
                      status === \'unhealthy\' && "bg-red-100 text-red-600",
                      status === \'unknown\' && "bg-gray-100 text-gray-600"
                    )}>
                      {status === \'unhealthy\' ? <AlertTriangle className="h-5 w-5" /> : <Server className="h-5 w-5" />}
                    </div>
                    <div>
                      <CardTitle className="text-lg font-semibold text-gray-900 dark:text-white">
                        {service.name}
                      </CardTitle>
                      <p className="text-xs text-gray-500 dark:text-gray-400">{service.baseUrl}</p>
                    </div>
                  </div>
                  {renderStatus(status)}
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-gray-600 dark:text-gray-300">{service.description}</p>
                <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                  <div className="flex items-center gap-1">
                    <Activity className="h-4 w-4" />
                    {state?.responseTimeMs !== undefined ? `${state.responseTimeMs} ms` : \'— ms\'}
                  </div>
                  <span>Last check: {state?.checkedAt || \'Not checked yet\'}</span>
                </div>
                {state?.details && (
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {state.details}
                  </p>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
