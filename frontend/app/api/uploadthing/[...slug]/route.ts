import { createRouteHandler } from "uploadthing/next"
import { ourFileRouter } from "../core"

/**
 * UploadThing v7+ requires a catch-all segment so presigned URL and upload
 * callbacks resolve (e.g. /api/uploadthing/...). A single route.ts is not enough.
 */
export const { GET, POST } = createRouteHandler({
  router: ourFileRouter,
})
