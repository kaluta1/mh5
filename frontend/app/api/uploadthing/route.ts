import { createRouteHandler } from "uploadthing/next"
import { ourFileRouter } from "./core"

/**
 * Root `/api/uploadthing` endpoint for clients that call uploadthing with
 * query params and no additional path segment.
 */
export const { GET, POST } = createRouteHandler({
  router: ourFileRouter,
})
