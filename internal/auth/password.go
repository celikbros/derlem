package auth

import "golang.org/x/crypto/bcrypt"

var dummyPasswordHash = func() string {
	hash, err := HashPassword("derlem-dummy-password-not-used-for-login")
	if err != nil {
		panic(err)
	}
	return hash
}()

func HashPassword(password string) (string, error) {
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return "", err
	}
	return string(hash), nil
}

func CheckPassword(hash, password string) bool {
	if hash == "" {
		hash = dummyPasswordHash
	}
	return bcrypt.CompareHashAndPassword([]byte(hash), []byte(password)) == nil
}
