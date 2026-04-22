import { createRouteHandler } from "uploadthing/next"
import { ourFileRouter } from "@/app/api/uploadthing/core"

/**
 * Root `/ut` endpoint for clients that call uploadthing with query params
 * (e.g. `/ut?actionType=upload&slug=profileAvatar`) and no path segment.
 */
export const { GET, POST } = createRouteHandler({
  router: ourFileRouter,
})
