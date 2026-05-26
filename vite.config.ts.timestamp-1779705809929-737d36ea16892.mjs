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
    include: ["plotly.js"]
  },
  resolve: {
    alias: {
      "@": path.resolve(__vite_injected_original_dirname, "./src")
    }
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvaG9tZS93ZW4vcHJvamVjdHMvUEFcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfZmlsZW5hbWUgPSBcIi9ob21lL3dlbi9wcm9qZWN0cy9QQS92aXRlLmNvbmZpZy50c1wiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9pbXBvcnRfbWV0YV91cmwgPSBcImZpbGU6Ly8vaG9tZS93ZW4vcHJvamVjdHMvUEEvdml0ZS5jb25maWcudHNcIjtpbXBvcnQgcGF0aCBmcm9tIFwicGF0aFwiXG5pbXBvcnQgZnMgZnJvbSBcImZzXCJcbmltcG9ydCB0YWlsd2luZGNzcyBmcm9tIFwiQHRhaWx3aW5kY3NzL3ZpdGVcIlxuaW1wb3J0IHJlYWN0IGZyb20gXCJAdml0ZWpzL3BsdWdpbi1yZWFjdFwiXG5pbXBvcnQgeyBkZWZpbmVDb25maWcgfSBmcm9tIFwidml0ZVwiXG5cbi8vIGh0dHBzOi8vdml0ZS5kZXYvY29uZmlnL1xuZXhwb3J0IGRlZmF1bHQgZGVmaW5lQ29uZmlnKHtcbiAgYmFzZTogJy8nLFxuICBwbHVnaW5zOiBbXG4gICAgcmVhY3QoKSxcbiAgICB0YWlsd2luZGNzcygpLFxuICAgIHtcbiAgICAgIG5hbWU6ICdzZXJ2ZS1kYXRhLWRpcicsXG4gICAgICBjb25maWd1cmVTZXJ2ZXIoc2VydmVyKSB7XG4gICAgICAgIHNlcnZlci5taWRkbGV3YXJlcy51c2UoKHJlcTogYW55LCByZXM6IGFueSwgbmV4dDogYW55KSA9PiB7XG4gICAgICAgICAgaWYgKCFyZXEudXJsPy5zdGFydHNXaXRoKCcvZGF0YS8nKSkgeyBuZXh0KCk7IHJldHVybjsgfVxuICAgICAgICAgIGNvbnN0IGZpbGVQYXRoID0gcGF0aC5qb2luKF9fZGlybmFtZSwgcmVxLnVybC5zcGxpdCgnPycpWzBdKTtcbiAgICAgICAgICB0cnkge1xuICAgICAgICAgICAgY29uc3Qgc3RhdCA9IGZzLnN0YXRTeW5jKGZpbGVQYXRoKTtcbiAgICAgICAgICAgIGlmIChzdGF0LmlzRmlsZSgpKSB7XG4gICAgICAgICAgICAgIGNvbnN0IGV4dCA9IHBhdGguZXh0bmFtZShmaWxlUGF0aCk7XG4gICAgICAgICAgICAgIGNvbnN0IG1pbWU6IFJlY29yZDxzdHJpbmcsIHN0cmluZz4gPSB7XG4gICAgICAgICAgICAgICAgJy5odG1sJzogJ3RleHQvaHRtbCcsXG4gICAgICAgICAgICAgICAgJy5qc29uJzogJ2FwcGxpY2F0aW9uL2pzb24nLFxuICAgICAgICAgICAgICAgICcuanMnOiAnYXBwbGljYXRpb24vamF2YXNjcmlwdCcsXG4gICAgICAgICAgICAgIH07XG4gICAgICAgICAgICAgIHJlcy5zZXRIZWFkZXIoJ0NvbnRlbnQtVHlwZScsIG1pbWVbZXh0XSA/PyAnYXBwbGljYXRpb24vb2N0ZXQtc3RyZWFtJyk7XG4gICAgICAgICAgICAgIGZzLmNyZWF0ZVJlYWRTdHJlYW0oZmlsZVBhdGgpLnBpcGUocmVzKTtcbiAgICAgICAgICAgICAgcmV0dXJuO1xuICAgICAgICAgICAgfVxuICAgICAgICAgIH0gY2F0Y2ggeyAvKiBmaWxlIG5vdCBmb3VuZCwgZmFsbCB0aHJvdWdoICovIH1cbiAgICAgICAgICBuZXh0KCk7XG4gICAgICAgIH0pO1xuICAgICAgfSxcbiAgICB9LFxuICBdLFxuICBkZWZpbmU6IHtcbiAgICBnbG9iYWw6ICdnbG9iYWxUaGlzJyxcbiAgfSxcbiAgb3B0aW1pemVEZXBzOiB7XG4gICAgaW5jbHVkZTogWydwbG90bHkuanMnXSxcbiAgfSxcbiAgcmVzb2x2ZToge1xuICAgIGFsaWFzOiB7XG4gICAgICBcIkBcIjogcGF0aC5yZXNvbHZlKF9fZGlybmFtZSwgXCIuL3NyY1wiKSxcbiAgICB9LFxuICB9LFxufSlcbiJdLAogICJtYXBwaW5ncyI6ICI7QUFBaVAsT0FBTyxVQUFVO0FBQ2xRLE9BQU8sUUFBUTtBQUNmLE9BQU8saUJBQWlCO0FBQ3hCLE9BQU8sV0FBVztBQUNsQixTQUFTLG9CQUFvQjtBQUo3QixJQUFNLG1DQUFtQztBQU96QyxJQUFPLHNCQUFRLGFBQWE7QUFBQSxFQUMxQixNQUFNO0FBQUEsRUFDTixTQUFTO0FBQUEsSUFDUCxNQUFNO0FBQUEsSUFDTixZQUFZO0FBQUEsSUFDWjtBQUFBLE1BQ0UsTUFBTTtBQUFBLE1BQ04sZ0JBQWdCLFFBQVE7QUFDdEIsZUFBTyxZQUFZLElBQUksQ0FBQyxLQUFVLEtBQVUsU0FBYztBQUN4RCxjQUFJLENBQUMsSUFBSSxLQUFLLFdBQVcsUUFBUSxHQUFHO0FBQUUsaUJBQUs7QUFBRztBQUFBLFVBQVE7QUFDdEQsZ0JBQU0sV0FBVyxLQUFLLEtBQUssa0NBQVcsSUFBSSxJQUFJLE1BQU0sR0FBRyxFQUFFLENBQUMsQ0FBQztBQUMzRCxjQUFJO0FBQ0Ysa0JBQU0sT0FBTyxHQUFHLFNBQVMsUUFBUTtBQUNqQyxnQkFBSSxLQUFLLE9BQU8sR0FBRztBQUNqQixvQkFBTSxNQUFNLEtBQUssUUFBUSxRQUFRO0FBQ2pDLG9CQUFNLE9BQStCO0FBQUEsZ0JBQ25DLFNBQVM7QUFBQSxnQkFDVCxTQUFTO0FBQUEsZ0JBQ1QsT0FBTztBQUFBLGNBQ1Q7QUFDQSxrQkFBSSxVQUFVLGdCQUFnQixLQUFLLEdBQUcsS0FBSywwQkFBMEI7QUFDckUsaUJBQUcsaUJBQWlCLFFBQVEsRUFBRSxLQUFLLEdBQUc7QUFDdEM7QUFBQSxZQUNGO0FBQUEsVUFDRixRQUFRO0FBQUEsVUFBcUM7QUFDN0MsZUFBSztBQUFBLFFBQ1AsQ0FBQztBQUFBLE1BQ0g7QUFBQSxJQUNGO0FBQUEsRUFDRjtBQUFBLEVBQ0EsUUFBUTtBQUFBLElBQ04sUUFBUTtBQUFBLEVBQ1Y7QUFBQSxFQUNBLGNBQWM7QUFBQSxJQUNaLFNBQVMsQ0FBQyxXQUFXO0FBQUEsRUFDdkI7QUFBQSxFQUNBLFNBQVM7QUFBQSxJQUNQLE9BQU87QUFBQSxNQUNMLEtBQUssS0FBSyxRQUFRLGtDQUFXLE9BQU87QUFBQSxJQUN0QztBQUFBLEVBQ0Y7QUFDRixDQUFDOyIsCiAgIm5hbWVzIjogW10KfQo=
