import { createUploadthing, type FileRouter } from "uploadthing/next";
import { UploadThingError } from "uploadthing/server";

const f = createUploadthing();

/**
 * Middleware pour vérifier l'authentification
 */
const auth = async (req: Request) => {
  try {
    let accessToken: string | undefined;

    // 1. Essayer de récupérer le token depuis le header Authorization
    const authHeader = req.headers.get("authorization");
    if (authHeader?.startsWith("Bearer ")) {
      accessToken = authHeader.substring(7);
    }

    // 2. Si pas de token dans Authorization, chercher dans les cookies
    if (!accessToken) {
      const cookieHeader = req.headers.get("cookie") || "";
      const cookies = Object.fromEntries(
        cookieHeader.split("; ").map(c => {
          const [key, value] = c.split("=");
          return [key, value];
        })
      );
      accessToken = cookies["access_token"] || cookies["token"];
    }

    // 3. Si toujours pas de token, essayer de le récupérer depuis les headers personnalisés
    if (!accessToken) {
      accessToken = req.headers.get("x-access-token") || undefined;
    }

    // 4. Si toujours pas de token, essayer depuis x-token header
    if (!accessToken) {
      accessToken = req.headers.get("x-token") || undefined;
    }

    if (!accessToken) {
      console.warn("No access token found in Authorization header, cookies, or custom headers");
      console.warn("Available headers:", Array.from(req.headers.entries()).map(([k, v]) => `${k}: ${v.substring(0, 50)}`));
      throw new UploadThingError("Unauthorized: No access token found");
    }

    console.log("Access token found, length:", accessToken.length);

    // Appeler l'endpoint /me pour vérifier le token et récupérer l'utilisateur
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const meResponse = await fetch(`${apiUrl}/api/v1/auth/me`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${accessToken}`,
        "Content-Type": "application/json"
      }
    });

    if (!meResponse.ok) {
      console.warn(`Auth endpoint returned ${meResponse.status}`);
      const errorText = await meResponse.text();
      console.warn("Auth error response:", errorText);
      throw new UploadThingError("Unauthorized: Invalid token");
    }

    const user = await meResponse.json();
    console.log("User authenticated:", user.id || user.userId);
    
    return { userId: user.id || user.userId };
  } catch (error) {
    console.error("Auth error:", error);
    throw new UploadThingError("Unauthorized");
  }
};

/**
 * FileRouter pour Uploadthing
 */
export const ourFileRouter = {
  /**
   * Route pour uploader les documents KYC
   */
  kycDocumentUploader: f({
    image: { maxFileSize: "1MB" }
  })
    .middleware(async ({ req }) => {
      // Vérifier l'authentification
      const user = await auth(req);
      return user;
    })
    .onUploadComplete(async ({ metadata, file }) => {
      console.log("File uploaded successfully:", file);
      
      return {
        uploadedBy: metadata.userId,
        url: file.url,
        name: file.name,
        size: file.size,
        type: file.type
      };
    }),

  /**
   * Route pour uploader les images de profil
   */
  profileImageUploader: f({
    image: { maxFileSize: "1MB", maxFileCount: 1 }
  })
    .middleware(async ({ req }) => {
      const user = await auth(req);
      return user;
    })
    .onUploadComplete(async ({ metadata, file }) => {
      console.log("Profile image uploaded:", file);
      
      return {
        uploadedBy: metadata.userId,
        url: file.url,
        name: file.name
      };
    }),

  /**
   * Route pour uploader les avatars de profil
   */
  profileAvatar: f({
    image: { maxFileSize: "2MB", maxFileCount: 1 }
  })
    .middleware(async ({ req }) => {
      const user = await auth(req);
      return user;
    })
    .onUploadComplete(async ({ metadata, file }) => {
      console.log("Profile avatar uploaded:", file);
      
      return {
        uploadedBy: metadata.userId,
        url: file.url,
        name: file.name
      };
    }),

  /**
   * Route pour uploader les documents de participation
   */
  participationDocumentUploader: f({
    image: { maxFileSize: "1MB" },
    video: { maxFileSize: "1MB" },
    pdf: { maxFileSize: "1MB" },
    blob: { maxFileSize: "1MB" }
  })
    .middleware(async ({ req }) => {
      const user = await auth(req);
      return user;
    })
    .onUploadComplete(async ({ metadata, file }) => {
      console.log("Participation document uploaded:", file);
      
      return {
        uploadedBy: metadata.userId,
        url: file.url,
        name: file.name,
        size: file.size,
        type: file.type
      };
    }),

  /**
   * Route pour uploader les médias de candidature (images et vidéos)
   */
  contestantMedia: f({
    image: { maxFileSize: "8MB", maxFileCount: 10 },
    video: { maxFileSize: "32MB", maxFileCount: 1 }
  })
    .middleware(async ({ req }) => {
      const user = await auth(req);
      return user;
    })
    .onUploadComplete(async ({ metadata, file }) => {
      console.log("Contestant media uploaded:", file);
      
      return {
        uploadedBy: metadata.userId,
        url: file.url,
        name: file.name,
        size: file.size,
        type: file.type
      };
    })
} satisfies FileRouter;

export type OurFileRouter = typeof ourFileRouter;
