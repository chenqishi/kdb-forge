# test_no_activation_never_stops_services

Inputs: temporary backup without activation journal and --execute. Outputs: actual main reports not activated, no psutil inspection/kill/Popen. This prevents accidental rollback of still-running legacy services before cutover. No persistent production side effects.
