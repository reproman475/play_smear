import React, { useState } from 'react';
import { withRouter } from 'react-router-dom';
import { Radio, Button, Modal } from 'antd';
import axios from 'axios';

import PlayerDisplay from './PlayerDisplay';
import CardDisplay from './CardDisplay';
import HandResults from './HandResults';
import getErrorString from './utils';

const RadioButton = Radio.Button;
const RadioGroup = Radio.Group;


function Trick(props) {
  const [cardSelected, setCardSelected] = useState();
  const [trickAcknowledged, setTrickAcknowledged] = useState(false);
  const {game, loading, setLoading, reloadGame, signedInUser, cards, setCards} = props;
  const myPlayer = game.players.find(player => player.user === signedInUser.id)?.id;

  function submitSpecificCard(card) {
    //console.log(card);
    if (loading) {
      return;
    }
    setLoading(true);
    axios.post(`/api/smear/v1/games/${game.id}/hands/${game.current_hand.id}/tricks/${game.current_trick.id}/plays/`,
      { card: card }
    ).then((response) => {
      const newCards = cards.filter(item => item !== card);
      setCards(newCards);
      reloadGame(false, true, true);
    }).catch((error) => {
      console.log(error);
      setLoading(false);
      Modal.error({
        title: "Unable to submit card to play",
        content: getErrorString(error.response.data),
        maskClosable: true,
      })
    });
  }

  // eslint-disable-next-line
  function submitCard() {
    return submitSpecificCard(cardSelected);
  }

  function clickCard(card) {
    if (cardSelected === card) {
      // This is a second click
      submitSpecificCard(cardSelected);
    } else {
      setCardSelected(card);
    }
  }

  function nextTrick() {
    if (game.current_trick.num === 6) {
      setTrickAcknowledged(true);
    } else {
      reloadGame(true, true, true);
    }
  }

  const player = game.players.find(player => player.id === game?.current_trick?.active_player);
  const waitingForTurn = (
    <>
      <p>Waiting for {player?.name} to play</p>
    </>
  );
  const taker = game.players.find(player => player.id === game.current_trick.taker);
  const trickFinishedPrompt = (
    <>
      <p>Trick is finished, {taker?.name} took the trick.</p>
      <Button onClick={nextTrick} disabled={loading}>Continue</Button>
    </>
  );
  const promptUserToPlay = (
    <>
      <p>Your turn, select a card to play</p>
    </>
  );
  const trickIsFinished = Boolean(game.current_trick.taker);
  const handIsFinished = Boolean(game.current_hand.results);
  const myTurn = game.current_trick.active_player === myPlayer;
  return (
    <div>
      <PlayerDisplay {...props} />
      { !trickIsFinished && <CardDisplay {...props} cardSelected={cardSelected} clickCard={clickCard} /> }
      { !myTurn && !trickIsFinished && waitingForTurn }
      { myTurn && !trickIsFinished && promptUserToPlay }
      { !trickAcknowledged && trickIsFinished && trickFinishedPrompt }
      { trickAcknowledged && handIsFinished && <HandResults {...props} /> }
    </div>
  );
}

export default withRouter(Trick);
