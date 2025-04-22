
certs: cert.crt mid.crt expired_mid.crt ca2_root.crt

# Create expired sub divisions cert in the chain below root
expired_mid.crt: expired_mid.key ca.key
	openssl x509 -req -days 1 -passin pass:fake -in expired_mid.csr -CA ca_root.crt -CAkey ca.key -set_serial 01 -out expired_mid.crt

expired_mid.key: ca_root.crt   
	openssl req -newkey rsa:2048 -nodes -subj /C=US/ST=MA/L=Faketown/O=FakeVcon/OU=Division/CN=div.fakevcon.io/emailAddress=admin@fakevcon.org/subjectAltName=div.fakevcon.org -keyout expired_mid.key -out expired_mid.csr

# Create a sub divisions cert in the chain below root
cert.crt: private.key mid.key
	openssl x509 -req -days 3650 -passin pass:fake -in request.csr -CA mid.crt -CAkey mid.key -set_serial 01 -out cert.crt

private.key: mid.crt   
	openssl req -newkey rsa:2048 -nodes -subj /C=US/ST=MA/L=Faketown/O=FakeVcon/OU=Group/CN=grp.div.fakevcon.io/emailAddress=admin@fakevcon.org/subjectAltName=grp.div.fakevcon.org -keyout private.key -out request.csr

# Create a sub divisions cert in the chain below root
mid.crt: mid.key ca.key
	openssl x509 -req -days 3650 -passin pass:fake -in mid.csr -CA ca_root.crt -CAkey ca.key -set_serial 02 -out mid.crt

mid.key: ca_root.crt   
	openssl req -newkey rsa:2048 -nodes -subj /C=US/ST=MA/L=Faketown/O=FakeVcon/OU=Division/CN=div.fakevcon.io/emailAddress=admin@fakevcon.org/subjectAltName=div.fakevcon.org -keyout mid.key -out mid.csr

# Sign the CA
ca_root.crt: ca.key
	openssl req -new -x509 -passin pass:fake -days 3650 -key ca.key -subj /C=US/ST=MA/L=Faketown/O=FakeVcon\ Inc/OU=Corporate/CN=fakevcon.io/emailAddress=admin@fakevcon.org/subjectAltName=fakevcon.org -keyout root.key -out ca_root.crt

# Create certificate of authority (CA) key
ca.key: 
	openssl genrsa -des3 -passout pass:fake -out ca.key 4096
	chmod 600 ca.key

# Sign the second CA
ca2_root.crt: ca2.key
	openssl req -new -x509 -passin pass:fake -days 3650 -key ca2.key -subj /C=US/ST=MA/L=Faketown/O=FakeVcon\ Inc/OU=Corporate/CN=fakevcon.io/emailAddress=admin@fakevcon.org/subjectAltName=fakevcon.org -keyout root.key -out ca2_root.crt

# Create another certificate of authority (CA) key
ca2.key: 
	openssl genrsa -des3 -passout pass:fake -out ca2.key 4096
	chmod 600 ca2.key
