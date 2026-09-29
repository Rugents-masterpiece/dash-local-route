import unittest

from app import discover_services, format_bytes, read_system_stats


class DashboardTests(unittest.TestCase):
    def test_service_discovery_keeps_configured_local_services(self):
        services = discover_services()
        ports = {service["port"] for service in services}
        self.assertIn(7878, ports)
        self.assertIn(9119, ports)
        names = {service["name"] for service in services}
        self.assertIn("LiteLLM", names)
        self.assertIn("Portainer", names)
        self.assertIn("SearXNG", names)
        self.assertIn("Peppol features", names)
        self.assertIn("Qwen Prisma", names)
        self.assertIn("Gemma 4 26B-A4B QAT", names)
        self.assertIn("Qwen3 Embedding 0.6B", names)
        self.assertIn("Qwen3 Reranker 0.6B", names)
        self.assertIn("Hermes Gateway API", names)
        self.assertIn("Prometheus", names)
        self.assertIn("OpenHands Agent Canvas", names)
        self.assertEqual(next(s for s in services if s["name"] == "OpenHands Agent Canvas")["url"], "http://192.168.16.42:8000/")

        self.assertIn("Grafana · Hetzner Cloud", names)
        self.assertEqual(services[0]["name"], "Peppol features")
        self.assertEqual(next(s for s in services if s["name"] == "Gemma 4 26B-A4B QAT")["url"], "http://192.168.16.42:8001/v1/models")
        self.assertEqual(next(s for s in services if s["name"] == "LiteLLM")["url"], "http://192.168.16.42:4000/ui/")
        self.assertEqual(next(s for s in services if s["name"] == "Prometheus")["url"], "http://192.168.16.42:9090")

        self.assertEqual(next(s for s in services if s["name"] == "Grafana · Hetzner Cloud")["url"], "http://192.168.16.164:3000/d/ad7ghz7/my-htzner-dash?from=now-6h&to=now&timezone=browser&var-filter0=&dtab=New-tab")
        self.assertTrue(next(s for s in services if s["name"] == "Firecrawl API")["kind"] == "api")
        self.assertNotIn("cAdvisor", names)
        self.assertTrue(all(service["url"].startswith(("http", "/proxy/")) for service in services))

    def test_format_bytes_is_human_readable(self):
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(1024), "1.0 KB")

    def test_system_stats_have_expected_fields(self):
        stats = read_system_stats()
        self.assertIn("memory", stats)
        self.assertIn("cpu_percent", stats)
        self.assertIn("processes", stats)

    def test_system_stats_have_both_nvidia_gpu_metrics(self):
        stats = read_system_stats()
        gpus = stats["gpu"]["nvidia"]
        self.assertGreaterEqual(len(gpus), 2)
        self.assertEqual(gpus[0]["vendor"], "NVIDIA")
        self.assertEqual(gpus[1]["vendor"], "NVIDIA")
        self.assertIn("name", gpus[0])
        self.assertIn("pci_bus_id", gpus[1])
        for metric in gpus:
            self.assertIn("percent", metric)
            self.assertIn("vram_used", metric)
            self.assertIn("vram_total", metric)
            self.assertIn("vram_percent", metric)
            self.assertIn("available", metric)
            self.assertTrue(metric["percent"] is None or isinstance(metric["percent"], (int, float)))



if __name__ == "__main__":
    unittest.main()
