var srpApp = angular.module('srpApp', [
  'ngRoute',
  'srpControllers',
  'soundServices',
  'ui.bootstrap'
]);

srpApp.config(['$routeProvider',
  function($routeProvider) {
    $routeProvider.
      when('/characters/:page?', {
        templateUrl: 'templates/characters.html',
        controller: 'CharactersController'
      }).
      when('/kills/:page?', {
        templateUrl: 'templates/kills.html',
        controller: 'KillsController'
      }).
      when('/payments/:page?', {
        templateUrl: 'templates/payments.html',
        controller: 'PaymentsController'
      }).
      when('/kill/:killId', {
        templateUrl: 'templates/kill.html',
        controller: 'KillController'
      }).
      when('/character/:characterId', {
        templateUrl: 'templates/character.html',
        controller: 'CharacterController'
      }).
      when('/payment/:paymentId', {
        templateUrl: 'templates/payment.html',
        controller: 'PaymentController'
      }).
      otherwise({
        redirectTo: '/kills'
      });
  }]);
