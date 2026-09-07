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
        self.assertIn("Templator Peppol", names)
        self.assertIn("Qwen Prisma", names)
        self.assertIn("Nemo Rugent", names)
        self.assertIn("Hermes Gateway API", names)
        self.assertIn("Prometheus", names)
        self.assertIn("cAdvisor", names)
        self.assertIn("Grafana · Hetzner Cloud", names)
        self.assertEqual(next(s for s in services if s["name"] == "LiteLLM")["url"], "http://192.168.16.42:4000/ui/")
        self.assertEqual(next(s for s in services if s["name"] == "Prometheus")["url"], "http://192.168.16.42:9090")
        self.assertEqual(next(s for s in services if s["name"] == "cAdvisor")["url"], "http://192.168.16.42:8080/metrics")
        self.assertEqual(next(s for s in services if s["name"] == "Grafana · Hetzner Cloud")["url"], "http://192.168.16.164:3000/d/ad7ghz7/my-htzner-dash?from=now-6h&to=now&timezone=browser&var-filter0=&dtab=New-tab")
        self.assertTrue(next(s for s in services if s["name"] == "Firecrawl API")["kind"] == "api")
        self.assertTrue(next(s for s in services if s["name"] == "cAdvisor")["kind"] == "api")
        self.assertTrue(all(service["url"].startswith("http") for service in services))

    def test_format_bytes_is_human_readable(self):
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(1024), "1.0 KB")

    def test_system_stats_have_expected_fields(self):
        stats = read_system_stats()
        self.assertIn("memory", stats)
        self.assertIn("cpu_percent", stats)
        self.assertIn("processes", stats)

    def test_system_stats_have_separate_nvidia_and_amd_gpu_metrics(self):
        stats = read_system_stats()
        self.assertIn("gpu", stats)
        self.assertIn("nvidia", stats["gpu"])
        self.assertIn("amd", stats["gpu"])
        for vendor in ("nvidia", "amd"):
            metric = stats["gpu"][vendor]
            self.assertIn("percent", metric)
            self.assertIn("vram_used", metric)
            self.assertIn("vram_total", metric)
            self.assertIn("vram_percent", metric)
            self.assertIn("available", metric)
            self.assertTrue(metric["percent"] is None or isinstance(metric["percent"], (int, float)))

    def test_parse_radeontop_reads_vram_usage(self):
        from app import _parse_radeontop_utilization

        metric = _parse_radeontop_utilization("123.4: bus 23, gpu 12.50%, vram 25.00% 512.00mb")
        self.assertEqual(metric["percent"], 12.5)
        self.assertEqual(metric["vram_used"], 512 * 1024 * 1024)
        self.assertEqual(metric["vram_total"], 2048 * 1024 * 1024)
        self.assertEqual(metric["vram_percent"], 25.0)

    def test_parse_radeontop_utilization(self):
        from app import _parse_radeontop_utilization

        metric = _parse_radeontop_utilization("123.4: bus 23, gpu 12.50%, ee 0.00%")
        self.assertEqual(metric["vendor"], "AMD")
        self.assertEqual(metric["percent"], 12.5)
        self.assertTrue(metric["available"])

    def test_parse_gpu_utilization_keeps_vendor_values_separate(self):
        from app import _parse_gpu_utilization

        parsed = _parse_gpu_utilization("NVIDIA GeForce RTX 4060 Ti, 37\n", "NVIDIA")
        self.assertEqual(parsed["vendor"], "NVIDIA")
        self.assertEqual(parsed["percent"], 37.0)
        self.assertTrue(parsed["available"])

        unavailable = _parse_gpu_utilization("", "AMD")
        self.assertEqual(unavailable["vendor"], "AMD")
        self.assertIsNone(unavailable["percent"])
        self.assertFalse(unavailable["available"])


if __name__ == "__main__":
    unittest.main()
