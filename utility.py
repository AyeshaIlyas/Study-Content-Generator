def write(filename, contents, mode="w"):
	with open(filename, mode) as file:
		file.write(contents)


def read(path):
	with open(path) as file:
		return file.read()


def read_binary(filename, chunk_size=5242880):
	with open(filename, 'rb') as _file:
		while True:
			data = _file.read(chunk_size)
			if not data:
				break
			yield data