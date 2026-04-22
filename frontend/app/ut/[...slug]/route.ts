import { createRouteHandler } from "uploadthing/next"
import { ourFileRouter } from "@/app/api/uploadthing/core"

/**
 * Direct `/ut/*` endpoint for UploadThing.
 * This avoids dependency on Next rewrites, which may be bypassed in some production proxies.
 */
export const { GET, POST } = createRouteHandler({
  router: ourFileRouter,
})
