# Live telemetry dashboard

The Pico can keep receiving and printing `PACKET:` lines over USB. Run this
dashboard on the computer connected to the Pico; it graphs every numeric
`Name: value unit` field in each packet.

1. Install the dashboard's serial dependency:

   ```text
   python -m pip install -r requirements-dashboard.txt
   ```

2. Connect the Pico by USB and close any other program using its serial port
   (such as Thonny's serial/REPL window).
3. Find the Pico's COM port in Windows Device Manager, then start the server
   from this folder, replacing `COM5` with that port:

   ```text
   python telemetry_dashboard.py --serial-port COM5
   ```

4. Find the computer's IPv4 address with `ipconfig`. On your phone, open
   `http://<computer-ip>:8000` while connected to the same Wi-Fi network.
   Allow Python through Windows Firewall on a private network if prompted.

The page shows the current value and a rolling graph for each field. Keep the
dashboard running while viewing it. The server is intended for a trusted local
network; it does not use a login.
