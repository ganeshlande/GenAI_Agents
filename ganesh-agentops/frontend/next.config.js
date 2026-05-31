/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required for the standalone Docker image output (used in production builds)
  // output: 'standalone',
  env: {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
    NEXT_PUBLIC_API_BASE_URL:
      process.env.NEXT_PUBLIC_API_BASE_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000",
  },
  webpack: (config) => {
    // Enable polling for hot-reload inside Docker on Windows/macOS
    config.watchOptions = {
      poll: 1000,
      aggregateTimeout: 300,
    };
    return config;
  },
};

module.exports = nextConfig;
