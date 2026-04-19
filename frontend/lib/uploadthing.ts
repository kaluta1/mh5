import { generateUploadButton, generateUploadDropzone } from "@uploadthing/react"
import type { OurFileRouter } from "@/app/api/uploadthing/core"

/** Must match Next route `app/api/uploadthing/[...slug]/route.ts` (not legacy `/ut`). */
const UPLOADTHING_URL =
  process.env.NEXT_PUBLIC_UPLOADTHING_URL?.replace(/\/+$/, "") || "/api/uploadthing"

export const UploadButton = generateUploadButton<OurFileRouter>({
  url: UPLOADTHING_URL,
})
export const UploadDropzone = generateUploadDropzone<OurFileRouter>({
  url: UPLOADTHING_URL,
})
