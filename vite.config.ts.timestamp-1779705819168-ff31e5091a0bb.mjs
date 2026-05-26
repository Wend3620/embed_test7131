// vite.config.ts
import path from "path";
import fs from "fs";
import tailwindcss from "file:///home/wen/projects/PA/node_modules/@tailwindcss/vite/dist/index.mjs";
import react from "file:///home/wen/projects/PA/node_modules/@vitejs/plugin-react/dist/index.js";
import { defineConfig } from "file:///home/wen/projects/PA/node_modules/vite/dist/node/index.js";
var __vite_injected_original_dirname = "/home/wen/projects/PA";
var vite_config_default = defineConfig({
  base: "/",
  plugins: [
    react(),
    tailwindcss(),
    {
      name: "serve-data-dir",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (!req.url?.startsWith("/data/")) {
            next();
            return;
          }
          const filePath = path.join(__vite_injected_original_dirname, req.url.split("?")[0]);
          try {
            const stat = fs.statSync(filePath);
            if (stat.isFile()) {
              const ext = path.extname(filePath);
              const mime = {
                ".html": "text/html",
                ".json": "application/json",
                ".js": "application/javascript"
              };
              res.setHeader("Content-Type", mime[ext] ?? "application/octet-stream");
              fs.createReadStream(filePath).pipe(res);
              return;
            }
          } catch {
          }
          next();
        });
      }
    }
  ],
  define: {
    global: "globalThis"
  },
  optimizeDeps: {
    include: ["plotly.js-dist"]
  },
  resolve: {
    alias: {
      "@": path.resolve(__vite_injected_original_dirname, "./src"),
      "plotly.js": "plotly.js-dist"
    }
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvaG9tZS93ZW4vcHJvamVjdHMvUEFcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfZmlsZW5hbWUgPSBcIi9ob21lL3dlbi9wcm9qZWN0cy9QQS92aXRlLmNvbmZpZy50c1wiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9pbXBvcnRfbWV0YV91cmwgPSBcImZpbGU6Ly8vaG9tZS93ZW4vcHJvamVjdHMvUEEvdml0ZS5jb25maWcudHNcIjtpbXBvcnQgcGF0aCBmcm9tIFwicGF0aFwiXG5pbXBvcnQgZnMgZnJvbSBcImZzXCJcbmltcG9ydCB0YWlsd2luZGNzcyBmcm9tIFwiQHRhaWx3aW5kY3NzL3ZpdGVcIlxuaW1wb3J0IHJlYWN0IGZyb20gXCJAdml0ZWpzL3BsdWdpbi1yZWFjdFwiXG5pbXBvcnQgeyBkZWZpbmVDb25maWcgfSBmcm9tIFwidml0ZVwiXG5cbi8vIGh0dHBzOi8vdml0ZS5kZXYvY29uZmlnL1xuZXhwb3J0IGRlZmF1bHQgZGVmaW5lQ29uZmlnKHtcbiAgYmFzZTogJy8nLFxuICBwbHVnaW5zOiBbXG4gICAgcmVhY3QoKSxcbiAgICB0YWlsd2luZGNzcygpLFxuICAgIHtcbiAgICAgIG5hbWU6ICdzZXJ2ZS1kYXRhLWRpcicsXG4gICAgICBjb25maWd1cmVTZXJ2ZXIoc2VydmVyKSB7XG4gICAgICAgIHNlcnZlci5taWRkbGV3YXJlcy51c2UoKHJlcTogYW55LCByZXM6IGFueSwgbmV4dDogYW55KSA9PiB7XG4gICAgICAgICAgaWYgKCFyZXEudXJsPy5zdGFydHNXaXRoKCcvZGF0YS8nKSkgeyBuZXh0KCk7IHJldHVybjsgfVxuICAgICAgICAgIGNvbnN0IGZpbGVQYXRoID0gcGF0aC5qb2luKF9fZGlybmFtZSwgcmVxLnVybC5zcGxpdCgnPycpWzBdKTtcbiAgICAgICAgICB0cnkge1xuICAgICAgICAgICAgY29uc3Qgc3RhdCA9IGZzLnN0YXRTeW5jKGZpbGVQYXRoKTtcbiAgICAgICAgICAgIGlmIChzdGF0LmlzRmlsZSgpKSB7XG4gICAgICAgICAgICAgIGNvbnN0IGV4dCA9IHBhdGguZXh0bmFtZShmaWxlUGF0aCk7XG4gICAgICAgICAgICAgIGNvbnN0IG1pbWU6IFJlY29yZDxzdHJpbmcsIHN0cmluZz4gPSB7XG4gICAgICAgICAgICAgICAgJy5odG1sJzogJ3RleHQvaHRtbCcsXG4gICAgICAgICAgICAgICAgJy5qc29uJzogJ2FwcGxpY2F0aW9uL2pzb24nLFxuICAgICAgICAgICAgICAgICcuanMnOiAnYXBwbGljYXRpb24vamF2YXNjcmlwdCcsXG4gICAgICAgICAgICAgIH07XG4gICAgICAgICAgICAgIHJlcy5zZXRIZWFkZXIoJ0NvbnRlbnQtVHlwZScsIG1pbWVbZXh0XSA/PyAnYXBwbGljYXRpb24vb2N0ZXQtc3RyZWFtJyk7XG4gICAgICAgICAgICAgIGZzLmNyZWF0ZVJlYWRTdHJlYW0oZmlsZVBhdGgpLnBpcGUocmVzKTtcbiAgICAgICAgICAgICAgcmV0dXJuO1xuICAgICAgICAgICAgfVxuICAgICAgICAgIH0gY2F0Y2ggeyAvKiBmaWxlIG5vdCBmb3VuZCwgZmFsbCB0aHJvdWdoICovIH1cbiAgICAgICAgICBuZXh0KCk7XG4gICAgICAgIH0pO1xuICAgICAgfSxcbiAgICB9LFxuICBdLFxuICBkZWZpbmU6IHtcbiAgICBnbG9iYWw6ICdnbG9iYWxUaGlzJyxcbiAgfSxcbiAgb3B0aW1pemVEZXBzOiB7XG4gICAgaW5jbHVkZTogWydwbG90bHkuanMtZGlzdCddLFxuICB9LFxuICByZXNvbHZlOiB7XG4gICAgYWxpYXM6IHtcbiAgICAgIFwiQFwiOiBwYXRoLnJlc29sdmUoX19kaXJuYW1lLCBcIi4vc3JjXCIpLFxuICAgICAgXCJwbG90bHkuanNcIjogXCJwbG90bHkuanMtZGlzdFwiLFxuICAgIH0sXG4gIH0sXG59KVxuIl0sCiAgIm1hcHBpbmdzIjogIjtBQUFpUCxPQUFPLFVBQVU7QUFDbFEsT0FBTyxRQUFRO0FBQ2YsT0FBTyxpQkFBaUI7QUFDeEIsT0FBTyxXQUFXO0FBQ2xCLFNBQVMsb0JBQW9CO0FBSjdCLElBQU0sbUNBQW1DO0FBT3pDLElBQU8sc0JBQVEsYUFBYTtBQUFBLEVBQzFCLE1BQU07QUFBQSxFQUNOLFNBQVM7QUFBQSxJQUNQLE1BQU07QUFBQSxJQUNOLFlBQVk7QUFBQSxJQUNaO0FBQUEsTUFDRSxNQUFNO0FBQUEsTUFDTixnQkFBZ0IsUUFBUTtBQUN0QixlQUFPLFlBQVksSUFBSSxDQUFDLEtBQVUsS0FBVSxTQUFjO0FBQ3hELGNBQUksQ0FBQyxJQUFJLEtBQUssV0FBVyxRQUFRLEdBQUc7QUFBRSxpQkFBSztBQUFHO0FBQUEsVUFBUTtBQUN0RCxnQkFBTSxXQUFXLEtBQUssS0FBSyxrQ0FBVyxJQUFJLElBQUksTUFBTSxHQUFHLEVBQUUsQ0FBQyxDQUFDO0FBQzNELGNBQUk7QUFDRixrQkFBTSxPQUFPLEdBQUcsU0FBUyxRQUFRO0FBQ2pDLGdCQUFJLEtBQUssT0FBTyxHQUFHO0FBQ2pCLG9CQUFNLE1BQU0sS0FBSyxRQUFRLFFBQVE7QUFDakMsb0JBQU0sT0FBK0I7QUFBQSxnQkFDbkMsU0FBUztBQUFBLGdCQUNULFNBQVM7QUFBQSxnQkFDVCxPQUFPO0FBQUEsY0FDVDtBQUNBLGtCQUFJLFVBQVUsZ0JBQWdCLEtBQUssR0FBRyxLQUFLLDBCQUEwQjtBQUNyRSxpQkFBRyxpQkFBaUIsUUFBUSxFQUFFLEtBQUssR0FBRztBQUN0QztBQUFBLFlBQ0Y7QUFBQSxVQUNGLFFBQVE7QUFBQSxVQUFxQztBQUM3QyxlQUFLO0FBQUEsUUFDUCxDQUFDO0FBQUEsTUFDSDtBQUFBLElBQ0Y7QUFBQSxFQUNGO0FBQUEsRUFDQSxRQUFRO0FBQUEsSUFDTixRQUFRO0FBQUEsRUFDVjtBQUFBLEVBQ0EsY0FBYztBQUFBLElBQ1osU0FBUyxDQUFDLGdCQUFnQjtBQUFBLEVBQzVCO0FBQUEsRUFDQSxTQUFTO0FBQUEsSUFDUCxPQUFPO0FBQUEsTUFDTCxLQUFLLEtBQUssUUFBUSxrQ0FBVyxPQUFPO0FBQUEsTUFDcEMsYUFBYTtBQUFBLElBQ2Y7QUFBQSxFQUNGO0FBQ0YsQ0FBQzsiLAogICJuYW1lcyI6IFtdCn0K
