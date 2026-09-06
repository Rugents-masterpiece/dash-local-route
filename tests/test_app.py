import unittest

from app import discover_services, format_bytes, read_system_stats


class DashboardTests(unittest.TestCase):
    def test_service_discovery_keeps_configured_local_services(self):
        services = discover_services()
        ports = {service["port"] for service in services}
        self.assertIn(7878, ports)
        self.assertIn(9119, ports)
        self.assertTrue(all(service["url"].startswith("http") for service in services))

    def test_format_bytes_is_human_readable(self):
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(1024), "1.0 KB")

    def test_system_stats_have_expected_fields(self):
        stats = read_system_stats()
        self.assertIn("memory", stats)
        self.assertIn("cpu_percent", stats)
        self.assertIn("processes", stats)


if __name__ == "__main__":
    unittest.main()
