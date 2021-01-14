package graph

// This file will be automatically regenerated based on the schema, any resolver implementations
// will be copied through when generating and any unknown code will be moved to the end.

import (
	"context"
	"fmt"
	"time"

	"gitlab.com/isard/isardvdi/backend/graph/generated"
)

func (r *subscriptionResolver) Desktopstate(ctx context.Context) (<-chan string, error) {
	ch := make(chan string)

	go func() {
		for {
			select {
			case <-ctx.Done():
				return

			default:
				time.Sleep(1 * time.Second)
				ch <- fmt.Sprintf("%s", time.Now())
			}
		}
	}()

	return ch, nil
}

// Subscription returns generated.SubscriptionResolver implementation.
func (r *Resolver) Subscription() generated.SubscriptionResolver { return &subscriptionResolver{r} }

type subscriptionResolver struct{ *Resolver }
