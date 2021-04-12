import json
import random
import socket
import string
import threading
import time

class Node(threading.Thread):
	def __init__(self, host, port, debug=False):
		super(Node, self).__init__()

		self.debug = debug

		self.terminate = threading.Event()

		self.host = host
		self.port = port

		self.inbound = []
		self.outbound = []

		self.id = self.make_id()

		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.start_server()

	def __str__(self):
		return "<Node " + self.id + " | " + self.host + " " + str(self.port) + ">"

	def debug_print(self, message):
		if self.debug:
			print(message)

	def make_id(self):
		generated_id = "".join((random.choice(string.ascii_uppercase) for x in range(5)))

		return generated_id

	def start_server(self):
		self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.sock.bind((self.host, self.port))
		self.sock.settimeout(10.0)
		self.sock.listen(1)

		debug_print("Node " + self.id + " started on " + self.host + ":" + str(self.port))

	def print_connections(self):
		print("CONNECTIONS\n")

		print(str(len(self.inbound)) + " INBOUND:\n")
		for connection in self.inbound:
			print(connection)

		print(str(len(self.outbound)) + " OUTBOUND:\n")
		for connection in self.outbound:
			print(connection)

	def clean_connections(self):
		for i in self.inbound:
			if i.terminate.is_set():
				self.on_i_disconnect(i)
				i.join()
				del self.inbound[self.inbound.index(i)]

		for i in self.outbound:
			if i.terminate.is_set():
				self.on_o_disconnect(i)
				i.join()
				del self.outbound[self.outbound.index(i)]

	def send_all(self, message, exclude=[]):
		for i in self.inbound:
			if i in exclude:
				pass
			else:
				self.send(i, message)

		for i in self.outbound:
			if i in exclude:
				pass
			else:
				self.send(i, message)

		debug_print("Sent " + str(message) + " to all connected nodes")

	def send(self, node, message):
		self.clean_connections()

		if node in self.inbound or node in self.outbound:
			try:
				node.send(message)

				debug_print("Sent " + str(message) + " to " + node.id)
			except Exception as e:
				debug_print(str(e))
		else:
			debug_print("Node not found")

	def connect(self, host, port):
		if host == self.host and port == self.port:
			debug_print("Cannot connect this node with itself")
			return False

		for node in self.outbound:
			if node.host == host and node.port == port:
				debug_print("Already connected to node " + node.id)
				return True

		try:
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			sock.connect((host, port))

			sock.send(self.id.encode("utf-8"))
			connected_node_id = sock.recv(4096).decode("utf-8")

			thread = self.create_connection(sock, connected_node_id, host, port)
			thread.start()

			self.outbound.append(thread)
			self.on_o_connect(thread)

			return thread

		except Exception as e:
			debug_print(str(e))

	def disconnect(self, node):
		if node in self.outbound:
			self.on_disconnect_request(node)
			node.stop()
			node.join()

			debug_print("Disconnected from node " + node.id)

			del self.outbound[self.outbound.index(node)]

		else:
			debug_print("Cannot disconnect from a node not connected")

	def stop(self):
		self.on_stop_request()
		self.terminate.set()

	def create_connection(self, connection, id, host, port):
		return Connection(self, connection, id, host, port)

	def run(self):
		while not self.terminate.is_set():
			try:
				connection, client_address = self.sock.accept()

				connected_node_id = connection.recv(4096).decode("utf-8")
				connection.send(self.id.encode("utf-8"))

				thread = self.create_connection(connection, connected_node_id, client_address[0], client_address[1])
				thread.start()

				self.inbound.append(thread)

				self.on_i_connect(thread)
                
			except socket.timeout:
				pass

			except Exception as e:
				debug_print(str(e))

		debug_print("Node stopping...")

		for t in self.inbound:
			t.stop()

		for t in self.outbound:
			t.stop()

		for t in self.inbound:
			t.join()

		for t in self.outbound:
			t.join()

		self.sock.settimeout(None)   
		self.sock.close()

		debug_print("Node stopped")

	def on_i_connect(self, node):
		print("Inbound node connected: " + node.id)

	def on_o_connect(self, node):
		print("Outbound node connected: " + node.id)

	def on_i_disconnect(self, node):
		print("Inbound node disconnected: " + node.id)

	def on_o_disconnect(self, node):
		print("Outbound node disconnected: " + node.id)

	def on_message(self, node, message):
		print("Message from " + node.id + ": " + str(message))

	def on_disconnect_request(self, node):
		print("Node wants to disconnect from: " + node.id)

	def on_stop_request(self):
		print("Node wants to stop")

class Connection(threading.Thread):
	def __init__(self, main_node, sock, id, host, port):
		super(Connection, self).__init__()

		self.host = host
		self.port = port
		self.main_node = main_node
		self.sock = sock
		self.terminate = threading.Event()

		self.id = id

		self.EOT_CHAR = 0x04.to_bytes(1, 'big')

		debug_print("Connection started with node " + self.id + " on " + self.host + ":" + str(self.port))

	def __str__(self):
		return "<Connection: " + self.main_node.host + ":" + str(self.main_node.port) + " <-> " + self.host + ":" + str(self.port) + ">"

	def send(self, data, encoding_type='utf-8'):
		if isinstance(data, str):
			self.sock.sendall(data.encode(encoding_type) + self.EOT_CHAR)

		elif isinstance(data, dict):
			try:
				json_data = json.dumps(data)
				json_data = json_data.encode(encoding_type) + self.EOT_CHAR
				self.sock.sendall(json_data)

			except TypeError as e:
				debug_print("Invalid dictionary: " + str(e))

			except Exception as e:
				debug_print(str(e))

		elif isinstance(data, bytes):
			bin_data = data + self.EOT_CHAR
			self.sock.sendall(bin_data)

		else:
			debug_print("Invalid data type")

	def stop(self):
		self.terminate.set()

	def parse_packet(self, packet):
		try:
			packet_decoded = packet.decode("utf-8")

			try:
				return json.loads(packet_decoded)

			except json.decoder.JSONDecodeError:
				return packet_decoded

		except UnicodeDecodeError:
			return packet

	def run(self):
		self.sock.settimeout(10.0)          
		buffer = b""

		while not self.terminate.is_set():
			chunk = b""

			try:
				chunk = self.sock.recv(4096) 

			except socket.timeout:
				pass

			except Exception as e:
				self.terminate.set()
				debug_print(str(e))

			if chunk != b"":
				buffer += chunk
				eot_pos = buffer.find(self.EOT_CHAR)

				while eot_pos > 0:
					packet = buffer[:eot_pos]
					buffer = buffer[eot_pos + 1:]

					self.main_node.on_message(self, self.parse_packet(packet))

					eot_pos = buffer.find(self.EOT_CHAR)

		self.sock.settimeout(None)
		self.sock.close()