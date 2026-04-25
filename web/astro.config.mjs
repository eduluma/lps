import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";
import { readFileSync } from "node:fs";

let APP_VERSION = "";
try {
    APP_VERSION = readFileSync(new URL("./version.txt", import.meta.url), "utf8").trim();
} catch { /* version.txt not present */ }

export default defineConfig({
    output: "server",
    site: "https://lps.eduluma.org",
    integrations: [tailwind()],
    server: { host: "0.0.0.0", port: 4321 },
    vite: {
        define: {
            "import.meta.env.APP_VERSION": JSON.stringify(APP_VERSION),
        },
        server: {
            allowedHosts: ["lps.eduluma.org", "lpsapi.eduluma.org"],
        },
    },
});
