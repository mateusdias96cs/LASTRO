/** @type {import('next').NextConfig} */
const nextConfig = {
  // `standalone` empacota só o necessário para rodar, o que mantém a imagem
  // pequena, mesmo critério da imagem da API.
  output: "standalone",
  reactStrictMode: true,
};

export default nextConfig;
