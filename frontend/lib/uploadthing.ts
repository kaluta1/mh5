import { generateUploadButton, generateUploadDropzone } from "@uploadthing/react";
import type { OurFileRouter } from "@/app/api/uploadthing/core";

export const UploadButton = generateUploadButton<OurFileRouter>({ url: "/ut" });
export const UploadDropzone = generateUploadDropzone<OurFileRouter>({ url: "/ut" });
