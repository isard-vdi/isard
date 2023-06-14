package isardvdi

func GetString(s *string) string {
	if s != nil {
		return *s
	}

	return ""
}

func GetInt(i *int) int {
	if i != nil {
		return *i
	}

	return -1
}

func GetBool(b *bool) bool {
	if b != nil {
		return *b
	}

	return false
}
