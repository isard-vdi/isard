package model

import "time"

type QuotaProfile struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	EntityID    int      `pg:",notnull"`
	Entity      *Entity  `pg:"rel:has-one"`
	Quotas      []*Quota `pg:"rel:has-many"`

	Users []*User `pg:"many2many:isardvdi_user_to_quota_profile"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type Quota struct {
	QuotaProfileID int           `pg:",pk,notnull"`
	QuotaProfile   *QuotaProfile `pg:"rel:has-one"`
	QuotaID        int           `pg:",pk,notnull"`
	Value          string        `pg:",notnull"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}
