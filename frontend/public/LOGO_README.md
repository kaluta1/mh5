# Official Logo Setup

## Adding Your Official Logo

To add your official logo to the application:

1. **Place your logo file** in the `frontend/public/` directory with the name `logo.png`
   - Recommended size: 512x512px (square)
   - Format: PNG with transparent background
   - File path: `frontend/public/logo.png`

2. **Logo Specifications:**
   - **Format**: PNG (with transparency preferred)
   - **Size**: 512x512px (will be scaled automatically)
   - **Aspect Ratio**: Square (1:1)
   - **Background**: Transparent or white
   - **File Name**: Must be `logo.png`

3. **Alternative Formats:**
   If you have a different format or name, you can:
   - Convert it to PNG
   - Rename it to `logo.png`
   - Or update the logo path in `frontend/components/ui/logo.tsx` (line 45)

## Logo Usage

The logo component (`Logo`) is used in:
- **Header** (`frontend/components/layout/header.tsx`)
- Can be used anywhere with: `<Logo size="md" showText={true} />`

## Logo Sizes

The logo component supports three sizes:
- `sm`: Small (24x24px icon)
- `md`: Medium (40x40px icon) - Default
- `lg`: Large (56x56px icon)

## Fallback Behavior

If `logo.png` doesn't exist, the component will automatically fall back to:
- A Heart icon with gradient background
- This ensures the site always displays something

## Testing

After adding your logo:
1. Place `logo.png` in `frontend/public/`
2. Restart your development server
3. Check the header - your logo should appear
4. If it doesn't load, check the browser console for errors

## Example Logo Component Usage

```tsx
import { Logo } from "@/components/ui/logo"

// Small logo without text
<Logo size="sm" showText={false} />

// Medium logo with text (default)
<Logo size="md" showText={true} href="/" />

// Large logo with custom link
<Logo size="lg" showText={true} href="/dashboard" />
```
