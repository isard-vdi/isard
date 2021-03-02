// https://docs.cypress.io/api/introduction/api.html

describe('Should login', () => {
  it('Loads the app on pc screen 1920 * 1080 ', () => {
    cy.viewport(1920, 1080);
    cy.visit('/');
    cy.get('.p-card-content').should('be.visible');
  });

  it('Fill in login credentials', () => {
    cy.get('#user').type('nefix').should('have.value', 'nefix');
    cy.get('#password').type('password').should('have.value', 'password');
  });

  it('Logs in and goes to users page', () => {
    cy.get('.p-button').click();

    cy.url().should('include', '/users');
  });
});
