package authentication

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/token"
)

func (a *Authentication) AcknowledgeDisclaimer(ctx context.Context, ss string) error {
	tkn, err := token.ParseDisclaimerAcknowledgementRequiredToken(a.Secret, ss)
	if err != nil {
		return err
	}

	u := model.User{
		ID:                     tkn.UserID,
		DisclaimerAcknowledged: true,
	}
	if err := u.UpdateDisclaimerAcknowledged(ctx, a.DB); err != nil {
		return fmt.Errorf("error updating the DB: %w", err)
	}

	return nil
}
