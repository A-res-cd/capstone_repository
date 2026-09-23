import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    server: {
      proxy: { '/api/v1': { target: env.CAPRE_DEV_SERVER || 'http://127.0.0.1:5000' } },
    },
    build: { target: 'es2022' },
  };
});
