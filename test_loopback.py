import pyaudiowpatch as pyaudio
import numpy as np
import time

p = pyaudio.PyAudio()

# Find loopback device
print("Buscando dispositivos loopback...")
for i in range(p.get_device_count()):
    dev = p.get_device_info_by_index(i)
    if dev.get('isLoopbackDevice'):
        print(f"[{i}] {dev['name']} - Loopback: True, Channels: {dev['maxInputChannels']}, Rate: {dev['defaultSampleRate']}")

# Try to get default loopback
try:
    wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    print(f"\nWASAPI info: {wasapi_info}")

    default_speakers = p.get_default_wasapi_loopback()
    print(f"\nDefault loopback: {default_speakers['name']}")
    print(f"Index: {default_speakers['index']}")
    print(f"Channels: {default_speakers['maxInputChannels']}")
    print(f"Rate: {default_speakers['defaultSampleRate']}")

    # Try recording with callback
    print("\nIntentando grabar 3 segundos con callback...")

    callback_count = [0]
    max_amplitude = [0]

    def callback(in_data, frame_count, time_info, status):
        callback_count[0] += 1
        audio_data = np.frombuffer(in_data, dtype=np.int16)
        max_amp = np.max(np.abs(audio_data))
        max_amplitude[0] = max(max_amplitude[0], max_amp)

        if callback_count[0] % 10 == 0:
            print(f"  Callback #{callback_count[0]}: {frame_count} frames, max amplitude: {max_amp}")

        return (in_data, pyaudio.paContinue)

    stream = p.open(
        format=pyaudio.paInt16,
        channels=int(default_speakers['maxInputChannels']),
        rate=int(default_speakers['defaultSampleRate']),
        input=True,
        input_device_index=default_speakers['index'],
        frames_per_buffer=1024,
        stream_callback=callback
    )

    print(f"Stream abierto: is_active={stream.is_active()}")
    stream.start_stream()
    print(f"Stream iniciado: is_active={stream.is_active()}")

    # Wait for 3 seconds
    time.sleep(3)

    stream.stop_stream()
    stream.close()

    print(f"\nResultados:")
    print(f"  Total callbacks: {callback_count[0]}")
    print(f"  Max amplitude detectada: {max_amplitude[0]}")

    if callback_count[0] == 0:
        print("\n[ERROR] El callback nunca fue llamado!")
        print("  Posibles causas:")
        print("  - PyAudioWPatch no esta correctamente instalado")
        print("  - El dispositivo no soporta loopback")
        print("  - Permisos de audio")
    elif max_amplitude[0] == 0:
        print("\n[WARNING] Callbacks recibidos pero sin senal de audio")
        print("  - Verifica que haya audio reproduciendose")
        print("  - Verifica el dispositivo de salida seleccionado")
    else:
        print(f"\n[SUCCESS] Audio capturado correctamente!")

except AttributeError as e:
    print(f"\n[ERROR] get_default_wasapi_loopback() no existe")
    print(f"Intentando metodo alternativo...")

    # Alternative method
    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_output = wasapi_info.get('defaultOutputDevice')

        if default_output is not None:
            speakers = p.get_device_info_by_index(default_output)
            print(f"\nDefault output device: {speakers['name']}")

            # Find corresponding loopback
            for i in range(p.get_device_count()):
                dev = p.get_device_info_by_index(i)
                if dev.get('isLoopbackDevice') and dev.get('name') == speakers['name']:
                    print(f"Found matching loopback at index {i}")
                    print(f"Intenta usar el índice {i} en tu app")
                    break
    except Exception as e2:
        print(f"Error en método alternativo: {e2}")

except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()

p.terminate()
print("\nTest completado.")
