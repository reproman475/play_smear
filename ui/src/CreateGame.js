import React, { Component } from 'react';
import { Redirect, withRouter } from 'react-router-dom';
import { Radio, Row, Checkbox, Input, Button, Modal, Spin } from 'antd';
import axios from 'axios';
import getErrorString from './utils';
import { signIn } from './auth_utils';
import './CreateGame.css';

const RadioButton = Radio.Button;
const RadioGroup = Radio.Group;

class CreateGame extends Component {

  state = {
    loading: false,
    redirectToGame: false,
    gameID: 0,
    visible: false,
    passcode: "",
    requirePasscode: false,
    numPlayers: null,
 //   numSpectators: null,
    numTeams: null,
    scoreToPlayTo: null,
    mustBidToWin: false,
  }

  createAnonymousUser(callNext) {
    var random_user;
    try {
      random_user = crypto.randomUUID();
    } catch (error) {
        Modal.error({
          title: "Unable to create anonymous user, please create a user and sign in, instead",
          content: getErrorString(error.response.data),
          maskClosable: true,
        })
        return;
    }
    var user_data = {"username": random_user, "password": random_user, "is_anonymous": "true"};

    axios.post('/api/users/v1/', user_data)
      .then((response) => {
        signIn(random_user, random_user, this.props.handleAuthChange, callNext);
        window.analytics.track("Anonymous User Created", {
          username: random_user,
        });
      })
      .catch((error) => {
        console.log(error);
        this.setState({
          loading: false,
        });
        Modal.error({
          title: "Unable to create anonymous user, please create a user and sign in, instead",
          content: getErrorString(error.response.data),
          maskClosable: true,
        })
      });
  }

  createGame() {
    var game_data = {
      passcode: this.state.passcode,
      num_players: this.state.numPlayers,
      // num_spectators: this.state.numSpectators,
      num_teams: this.state.numTeams ? this.state.numTeams : 0,
      score_to_play_to: this.state.scoreToPlayTo,
      single_player: this.props.single,
      must_bid_to_win: this.state.mustBidToWin,
    };
    axios.post('/api/smear/v1/games/', game_data)
      .then((response) => {
        window.analytics.track("Game Created", {
          "Game ID": response.data.id,
          "Number of players": game_data.num_players,
          "Number of Teams": game_data.num_teams,
          "Score to play to": game_data.score_to_play_to,
          "Must bid to win": game_data.must_bid_to_win,
          "Single player": game_data.single_player,
        });
        this.setState({
          gameID: response.data.id,
          redirectToGame: true,
          loading: false,
        });
      })
      .catch((error) => {
        console.log(error);
        this.setState({
          loading: false,
        });
        Modal.error({
          title: "Unable to create a new game",
          content: getErrorString(error.response.data),
          maskClosable: true,
        })
      });
  }

  handleCreate = () => {
    if (!this.readyToStart()) {
      return;
    }
    this.setState({
      loading: true
    });
    if (!this.props.signedIn) {
      // If we aren't signed in, create an anonymous user and then create the game
      this.createAnonymousUser(()=>{
        this.createGame();
      });
    } else {
      this.createGame();
    }
  }

  onChangeInput = (e) => {
    this.setState({[e.target.name]: e.target.value});
  }

  onChangeCheck = (e) => {
    this.setState({[e.target.name]: e.target.checked});
  }

  onCancel = () => {
    this.setState({
      visible: false,
      passcode: "",
      requirePasscode: false,
      numPlayers: null,
      numTeams: null,
      scoreToPlayTo: null,
      mustBidToWin: false,
    });
  }


  readyToStart = () => {
    return (
      (this.state.requirePasscode === false || (this.state.requirePasscode === true && this.state.passcode.length > 0)) &&
      (this.state.scoreToPlayTo && this.state.scoreToPlayTo > 0) &&
      (this.state.numPlayers && this.state.numPlayers > 0)
    );
  }

  render() {
    const buttonText = this.props.buttonText || "Create New Game";
    if (this.state.redirectToGame) {
      return <Redirect push to={`/games/${this.state.gameID}`} />
    }

    return (
      <div className="CreateGame">
        <div align="center">
          { this.state.loading && <Spin size="large" />}
        </div>
        <Modal
          title={`Start a ${this.props.single ? "single player" : "multiplayer"} game`}
          visible={this.state.visible}
          onOk={this.handleCreate}
          okText="Create Game"
          okButtonProps={{ disabled: !this.readyToStart()}}
          onCancel={this.onCancel}
        >
          <Row className="create_div">
            <p className="inputLabel">Total number of players:</p>
            <RadioGroup name="numPlayers" onChange={this.onChangeInput}>
              <RadioButton value="2">2</RadioButton>
              <RadioButton value="3">3</RadioButton>
              <RadioButton value="4">4</RadioButton>
              <RadioButton value="5">5</RadioButton>
              <RadioButton value="6">6</RadioButton>
              <RadioButton value="7">7</RadioButton>
              <RadioButton value="8">8</RadioButton>
            </RadioGroup>
          </Row>
          <p>{!this.props.single && "Note: computer players can be assigned in the next screen"}</p>
          <Row className="create_div">
            <p className="inputLabel">Number of teams:</p>
            <RadioGroup name="numTeams" onChange={this.onChangeInput}>
              <RadioButton value="0">No teams</RadioButton>
              <RadioButton value="2">2</RadioButton>
              <RadioButton value="3">3</RadioButton>
              <RadioButton value="4">4</RadioButton>
            </RadioGroup>
          </Row>
          <br/>
          <Row className="create_div">
            <p className="inputLabel">Score to play to:</p>
            <RadioGroup name="scoreToPlayTo" onChange={this.onChangeInput}>
              <RadioButton value="1">1</RadioButton>
              <RadioButton value="11">11</RadioButton>
              <RadioButton value="15">15</RadioButton>
              <RadioButton value="21">21</RadioButton>
            </RadioGroup>
          </Row>
          <br/>
          <Row className="create_div">
            <Checkbox
              value={this.state.mustBidToWin}
              name="mustBidToWin"
              onChange={this.onChangeCheck}
            >
              Require a winning bid to go out
            </Checkbox>
          </Row>
          <br/>
          { !this.props.single &&
          <Row type="flex" className="create_div">
            <Checkbox
              value={this.state.requirePasscode}
              name="requirePasscode"
              onChange={this.onChangeCheck}
            >
              Require passcode to join
            </Checkbox>
            <Input
              className="create_input"
              placeholder="Passcode"
              name="passcode"
              value={this.state.passcode}
              disabled={!this.state.requirePasscode}
              onChange={this.onChangeInput}
              onPressEnter={() => this.handleCreate()}
            />
          </Row>
          }
        </Modal>
        <div>
          <Button style={{width:250}} onClick={() => this.setState({visible: true})}>{buttonText}</Button>
        </div>
      </div>
    );
  }
}

export default withRouter(CreateGame);
