import pytest

def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """
    Hook to print execution times at the end of the test session.
    """
    # Try to get benchmark results from the session
    # The fixture can store them in session.config._benchmark_results
    results = getattr(config, "_benchmark_results", None)
    
    if not results:
        return

    terminalreporter.section("Pipeline Execution Times Summary")
    
    for doc_id, data in results.items():
        if "execution_times" in data:
            terminalreporter.write(f"\nDocument: {doc_id}\n")
            total_time = 0.0
            for step, seconds in data["execution_times"].items():
                terminalreporter.write(f"  {step:.<30} {seconds:7.4f}s\n")
                total_time += seconds
            terminalreporter.write(f"  {'Total pipeline time':.<30} {total_time:7.4f}s\n")
    
    terminalreporter.write("\n")
