from machine import SPI, Pin
from rfm69 import RFM69
import time

# Configure the pins
spi = SPI(0, miso=Pin(4), mosi=Pin(7), sck=Pin(6), baudrate=50000, polarity=0, phase=0, firstbit=SPI.MSB)
nss = Pin(5, Pin.OUT, value=True)
rst = Pin(3, Pin.OUT, value=False)

# Initiate the module
rfm = RFM69(spi=spi, nss=nss, reset=rst)
led = Pin(8, Pin.OUT)

# Set module parameters
rfm.frequency_mhz = 432.42 # MHz
rfm.node = 110

rfm.bitrate = 250000 # 250 Kbs
rfm.frequency_deviation = 250000 # 250 KHz
rfm.tx_power = 20 # 20 dBm maximum

# Optionally set an encryption key (16 byte AES key). MUST match both
# on the transmitter and receiver (or be set to None to disable/the default).
# rfm.encryption_key = ( b"\x01\x02\x03\x04\x05\x06\x07\x08\x01\x02\x03\x04\x05\x06\x07\x08" )
rfm.encryption_key = b"fhdt543wkslpovic"
 
 
# Print module parameters
print('Freq            :', rfm.frequency_mhz, 'MHz')
print('tx power        :', rfm.tx_power, 'dBm')
print('Encryption Key  :', rfm.encryption_key)
print('Freq. deviation :', rfm.frequency_deviation, 'Hz' )
print('bitrate         :', rfm.bitrate, 'bits/sec' )
print('Temperature     :', rfm.temperature, '°C\n' )

# Send a packet.  Note you can only send a packet up to 60 bytes in length.
# This is a limitation of the radio packet size, so if you need to send larger
# amounts of data you will need to break it into smaller send calls.  Each send
# call will wait for the previous one to finish before continuing.
# rfm.send(bytes("Un message", "utf-8"))

# Wait to receive packets.  Note that this library can't receive data at a fast
# rate, in fact it can only receive and process one 60 byte packet at a time.
# This means you should only use this for low bandwidth scenarios, like sending
# and receiving a single message at a time.
# Optionally change the receive timeout from its default of 0.5 seconds:
# packet = rfm.receive(timeout=5.0)
# If no packet was received during the timeout then None is returned.

try:
    while True:
        packet = rfm.receive()
        if packet is not None:
            try:
                decrypt_packet = packet.decode("ascii")
                print("PACKET:" + decrypt_packet)
                led.on()
            except UnicodeError:
                print("Received non-ASCII packet, skipping decode.")
        else:
            led.off()
        
        time.sleep(1)
finally:
    led.off()