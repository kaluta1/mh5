import { generateUploadButton, generateUploadDropzone } from "@uploadthing/react"
import type { OurFileRouter } from "@/app/api/uploadthing/core"

/** Must match route handlers via `/ut` rewrite or explicit env URL. */
const rawUploadthingUrl =
  process.env.NEXT_PUBLIC_UPLOADTHING_URL?.replace(/\/+$/, "") || ""

// In production, `/api/*` may be proxied to backend (FastAPI), which breaks UploadThing.
// Use `/ut` rewrite so requests still reach Next.js route handlers.
export const UPLOADTHING_URL =
  !rawUploadthingUrl || rawUploadthingUrl === "/api/uploadthing"
    ? "/ut"
    : rawUploadthingUrl

export const UploadButton = generateUploadButton<OurFileRouter>({
  url: UPLOADTHING_URL,
})
export const UploadDropzone = generateUploadDropzone<OurFileRouter>({
  url: UPLOADTHING_URL,
})
