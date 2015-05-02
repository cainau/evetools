var srpControllers = angular.module('srpControllers', [
  'soundServices', 'ui.bootstrap'
]);

displayDetails = function($scope, entity) {
  if (entity === null) {
      return;
  }
  if (!entity.character_id) {
      entity.name = entity.corporation_name;
      entity.group_name = entity.alliance_name;
      entity.image_32 = 'https://image.eveonline.com/Corporation/' + entity.corporation_id + '_32.png';
      entity.image_64 = 'https://image.eveonline.com/Corporation/' + entity.corporation_id + '_64.png';
      entity.image_128 = 'https://image.eveonline.com/Corporation/' + entity.corporation_id + '_128.png';
  } else if (!entity.alliance_id || entity.alliance_id == $scope.alliance_id) {
      entity.name = entity.character_name;
      entity.group_name = entity.corporation_name;
      entity.image_32 = 'https://image.eveonline.com/Character/' + entity.character_id + '_32.jpg';
      entity.image_64 = 'https://image.eveonline.com/Character/' + entity.character_id + '_64.jpg';
      entity.image_128 = 'https://image.eveonline.com/Character/' + entity.character_id + '_128.jpg';
  } else {
      entity.name = entity.character_name;
      entity.group_name = entity.alliance_name;
      entity.image_32 = 'https://image.eveonline.com/Character/' + entity.character_id + '_32.jpg';
      entity.image_64 = 'https://image.eveonline.com/Character/' + entity.character_id + '_64.jpg';
      entity.image_128 = 'https://image.eveonline.com/Character/' + entity.character_id + '_128.jpg';
  }
};

formatValue = function(value) {
    stages = [ '', 'k', 'M', 'B', 'T' ];
    for (i = 0; i < stages.length; i++) {
        if (value < 1000 || i == stages.length - 1) {
            return (Math.round(value * 100, 2) / 100) + stages[i];
        } else {
            value /= 1000;
        }
    }
};

srpControllers.controller('PaymentController', ['$scope', '$routeParams', '$location', 'Payment', 'Kill',
        function ($scope, $routeParams, $location, Payment, Kill) {
  $scope.payment = Payment.get({paymentId: $routeParams.paymentId}, function(payment) {
      payment.losses.forEach(function(loss) {
          Kill.get({killId: loss.kill_id}, function(kill) {
              loss.kill_time = kill.kill_time;
              loss.ship_type_id = kill.victim.ship_type_id;
              loss.ship_name = kill.victim.ship_name;
              loss.ship_class = kill.victim.ship_class;
              loss.loss_type = kill.loss_type;
          });
      });
  });
  $scope.navigate = function(kill_id) {
      $location.path('/kill/' + kill_id);
  };
}]);

srpControllers.controller('PaymentsController', ['$scope', '$routeParams', '$location', 'Payment',
        function($scope, $routeParams, $location, Payment) {
  $scope.setPage = function(page) {
      $scope.page = page;
      Payment.query({page: page, paid: false}, function(payments) {
          $scope.pages = [-2,-1,0,1,2].map(function(n) { return n + Math.max(3, page); });
          $scope.payments = payments;
      });
  }
  $scope.navigate = function(id) {
      $location.path('/payment/' + id);
  };
  $scope.setPage(parseInt($routeParams.page || 1));
}]);

srpControllers.controller('KillController', ['$scope', '$routeParams', 'Kill',
        function ($scope, $routeParams, Kill) {
  $scope.kill = Kill.get({killId: $routeParams.killId}, function(kill) {
      displayDetails($scope, kill.victim);
      displayDetails($scope, kill.final_blow);
      kill.attackers.forEach(function(attacker) { displayDetails($scope, attacker); });
      kill.grouped_items.highs.forEach(function(item) { item.value = formatValue(item.value); });
      kill.grouped_items.mids.forEach(function(item) { item.value = formatValue(item.value); });
      kill.grouped_items.lows.forEach(function(item) { item.value = formatValue(item.value); });
      kill.grouped_items.rigs.forEach(function(item) { item.value = formatValue(item.value); });
      kill.grouped_items.subsystems.forEach(function(item) { item.value = formatValue(item.value); });
      kill.grouped_items.cargo.forEach(function(item) { item.value = formatValue(item.value); });
      kill.grouped_items.fleet_hangar.forEach(function(item) { item.value = formatValue(item.value); });
      kill.grouped_items.specialized_hangar.forEach(function(item) { item.value = formatValue(item.value); });
      kill.grouped_items.implants.forEach(function(item) { item.value = formatValue(item.value); });
      kill.hull_value = formatValue(kill.hull_value);
      kill.dropped_value = formatValue(kill.dropped_value);
      kill.destroyed_value = formatValue(kill.destroyed_value);
      kill.total_value = formatValue(kill.total_value);
  });
}]);

srpControllers.controller('KillsController', ['$scope', '$routeParams', '$location', 'Kill',
        function ($scope, $routeParams, $location, Kill) {
  $scope.setPage = function(page) {
      $scope.page = page;
      Kill.query({page: page}, function(kills) {
          $scope.pages = [-2,-1,0,1,2].map(function(n) { return n + Math.max(3, page); });
          kills.forEach(function(kill) {
              displayDetails($scope, kill.victim);
              displayDetails($scope, kill.final_blow);
              kill.total_value = formatValue(kill.total_value);
          });
          $scope.kills = kills;
      });
  };
  $scope.navigate = function(id) {
    $location.path('/kill/' + id);
  };
  $scope.group = function(alliance_id, corp, alliance) {
      if (!alliance_id || alliance_id === $scope.alliance_id) {
          return corp;
      } else {
          return alliance;
      }
  };
  $scope.setPage(parseInt($routeParams.page || 1));
}]);

srpControllers.controller('AdminController', ['$scope', '$routeParams', '$location', 'Kill',
        function ($scope, $routeParams, $location, Kill) {
  if (!($scope.srp_admin)) {
      $location.path('/kills');
  }
  $scope.setLossType = function(kill, loss_type) {
      kill.loss_type = loss_type;
      if (loss_type === 'Awox' || loss_type === 'Cyno' || loss_type === 'Fit' || loss_type === 'PVE') {
          kill.srp_amount = 0;
      } else if (loss_type === 'Solo' && kill.victim.ship_class !== 'Frigate' && kill.victim.ship_class !== 'Destroyer') {
          kill.srp_amount = 0;
      } else if (kill.default_payment <= 40 || kill.loss_type === 'Stratop' || kill.home_region) {
          kill.srp_amount = kill.default_payment;
      } else {
          kill.srp_amount = 40;
      }
  };
  $scope.setPage = function(page) {
      $scope.page = page;
      Kill.query({page: page, srpable: true}, function(kills) {
          $scope.pages = [-2,-1,0,1,2].map(function(n) { return n + Math.max(3, page); });
          kills.forEach(function(kill) {
              Kill.get({killId: kill.kill_id, loss_attributes: true}, function(extra) {
                  kill.home_region = extra.loss_attributes.home_region;
              });
              displayDetails($scope, kill.victim);
              if (kill.loss_type) {
                  kill.processed = true;
              } else {
                  kill.processed = false;
                  kill.loss_type = kill.suggested_loss_type;
              }
              if (!kill.srp_amount) {
                  $scope.setLossType(kill, kill.loss_type);
              }
              kill.is_open = false;
              kill.save = function() {
                  kill.$save(function(kill, putResponseHeaders) {
                      kill.processed = true;
                  });
              };
          });
          $scope.kills = kills;
      });
  };
  $scope.navigate = function(id) {
    $location.path('/kill/' + id);
  };
  $scope.group = function(alliance_id, corp, alliance) {
      if (!alliance_id || alliance_id === $scope.alliance_id) {
          return corp;
      } else {
          return alliance;
      }
  };
  $scope.setPage(parseInt($routeParams.page || 1));
}]);

srpControllers.controller('CharacterController', ['$scope', '$routeParams', '$location', 'Character', 'Kill', 'Payment',
        function ($scope, $routeParams, $location, Character, Kill, Payment) {
  $scope.setKillsPage = function(page) {
      $scope.killsPage = page;
      Kill.query({victim: $routeParams.characterId, page: page}, function(kills) {
          $scope.killsPages = [-2,-1,0,1,2].map(function(n) { return n + Math.max(3, page); });
          $scope.losses = kills;
      });
  };
  $scope.character = Character.get({characterId: $routeParams.characterId});
  $scope.payments = Payment.query({cid: $routeParams.characterId});
  for (i = 0; i < $scope.payments.length; i++) {
      if ($scope.payments[i].paid === false) {
          $scope.current_payment = $scope.payments[i];
          $scope.payments.splice(i, 1);
          break;
      }
  }
  $scope.navigateKill = function(id) {
    $location.path('/kill/' + id);
  };
  $scope.setKillsPage(1);
}]);

srpControllers.controller('CharactersController', ['$scope', '$routeParams', '$location', 'Character',
        function ($scope, $routeParams, $location, Character) {
  $scope.setPage = function(page) {
      $scope.page = page;
      Character.query({page: page}, function(characters) {
          $scope.pages = [-2,-1,0,1,2].map(function(n) { return n + Math.max(3, $scope.page); });
          $scope.characters = characters;
      });
  };
  $scope.navigate = function(id) {
      $location.path('/character/' + id);
  };
  $scope.setPage(parseInt($routeParams.page || 1));
}]);

srpControllers.controller('NavbarController', ['$scope', '$rootScope', '$location', 'Config', 'Search',
        function($scope, $rootScope, $location, Config, Search) {
  Config.get({}, function(config) {
    $rootScope.logged_in = config.logged_in;
    $rootScope.alliance_id = config.alliance_id;
    if (config.logged_in) {
      $rootScope.character_id = config.character_id;
      $rootScope.character_name = config.character_name;
      $rootScope.srp_admin = config.srp_admin;
      $rootScope.srp_payer = config.srp_payer;
    }
  });
  $scope.searchValue = "";
  $scope.select = function(result) {
      switch (result.type) {
          case 'kill':
              $location.path('/kill/' + result.id);
              break;
          case 'character':
              $location.path('/character/' + result.id);
              break;
          case 'payment':
              $location.path('/payment/' + result.id);
              break;
      }
  };
  $scope.search = function(value) {
      return Search.query({searchText: value}).$promise;
  };
  $scope.submit = function() {
      if (typeof $scope.searchValue === 'string') {
          Search.query({searchText: $scope.searchValue}, function(results) {
              if (results.length > 0) {
                  $scope.select(results[0]);
              }
          });
      } else if (typeof $scope.searchValue === 'object') {
          $scope.select($scope.searchValue);
      }
  };
}]);

