var posmonApp = angular.module('posmonApp', [
  'ngRoute',
  'posmonControllers',
  'soundServices',
  'ui.bootstrap'
]);

posmonApp.config(['$routeProvider',
  function($routeProvider) {
    $routeProvider.
      when('/towers', {
        templateUrl: 'templates/towers.html',
        controller: 'TowersController',
        reloadOnSearch: false
      }).
      when('/towers/:towerId', {
        templateUrl: 'templates/tower.html',
        controller: 'TowerController'
      }).
      when('/posmon', {
        templateUrl: 'templates/posmon.html',
        controller: 'TowersController',
        reloadOnSearch: false
      }).
      otherwise({
        redirectTo: '/towers'
      });
  }]);
