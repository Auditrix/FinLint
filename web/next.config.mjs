/** @type {import('next').NextConfig} */
const nextConfig = {
  // Compiles to plain static files in out/, so the FastAPI app can serve the
  // whole frontend itself. One container, one deploy, one URL.
  output: "export",
  images: { unoptimized: true },
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
